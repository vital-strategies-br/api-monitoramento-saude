"""Carregador de resultados (.parquet) para o PostgreSQL.

O parquet deve conter as colunas:
- id_pessoa
- tipo_evento
- data_identificacao
- tipo_identificador
- valor_identificador

Este script popula as tabelas:
- monitoramento.individuo (id = id_pessoa)
- monitoramento.individuo_identificador
- monitoramento.individuo_evento

A carga de eventos é um upsert idempotente: o parquet é a fonte da
verdade para gera_alerta, e data_identificacao só avança. Requer a
migração V9, que cria o índice único das linhas sem origem. O relatório
final aponta quantos eventos já no banco estavam sem alerta apesar de o
parquet indicar alerta.

Para ler parquet, instale o extra:
    pip install .[loader]

Uso:
    python scripts/load_parquet.py --parquet /caminho/arquivo.parquet
    python scripts/load_parquet.py --parquet /caminho/pasta_com_parquets
    python scripts/load_parquet.py --parquet /caminho/arquivo.parquet --dry-run

Por padrão, o script usa a variável de ambiente DATABASE_URL.
"""

import argparse
import os
from datetime import date, datetime
from pathlib import Path
from typing import Iterable

import psycopg

try:
    import pyarrow.parquet as pq
except Exception as e:  # pragma: no cover
    pq = None  # type: ignore
    _PYARROW_IMPORT_ERROR = e


COLUMNS = [
    "id_pessoa",
    "tipo_evento",
    "metodo_identificacao",
    "data_identificacao",
    "tipo_identificador",
    "valor_identificador",
    "banco_origem_identificacao",
    "id_registro_identificacao",
    "gera_alerta",
]

BANCO_ORIGEM_IDENTIFICACAO_ENUM = set(["e-SUS APS", "Sinan - Violências"])

TEMP_TABLE = "staging_parquet_eventos"


def _dsn_for_psycopg(database_url: str) -> str:
    url = database_url.strip().strip('"').strip("'")

    if url.startswith("postgresql+psycopg://"):
        return "postgresql://" + url.removeprefix("postgresql+psycopg://")

    if url.startswith("postgresql+psycopg_async://"):
        return "postgresql://" + url.removeprefix("postgresql+psycopg_async://")

    return url


def _iter_parquet_files(path_str: str) -> list[Path]:
    path = Path(path_str)

    if path.is_dir():
        return sorted(path.rglob("*.parquet"))

    return [path]


def _normalize_dt(value) -> date:
    if value is None:
        raise TypeError("data_identificacao não pode ser None")

    if isinstance(value, date) and not isinstance(value, datetime):
        return value

    if isinstance(value, datetime):
        return value.date()

    if isinstance(value, (int, float)):
        return datetime.utcfromtimestamp(value).date()

    if isinstance(value, str):
        s = value.strip()
        # aceita ISO completo ou só data
        return date.fromisoformat(s[:10])

    raise TypeError(f"Tipo inválido para data_identificacao: {type(value)!r}")


def _validate_columns(file_path: Path, available: Iterable[str]) -> None:
    missing = set(COLUMNS).difference(set(available))
    if missing:
        cols = ", ".join(sorted(missing))
        raise ValueError(
            f"Parquet '{file_path}' não possui as colunas obrigatórias: {cols}"
        )


def _none_if_blank(v):
    if v is None:
        return None
    s = str(v).strip()
    if s == "":
        return None
    if s.lower() in {"nan", "none", "null"}:  # common “string-null” junk
        return None
    return s


def _normalize_banco_origem(v):
    s = _none_if_blank(v)
    if s is None:
        return None
    # normalize common whitespace issues
    s = " ".join(s.split())
    return s if s in BANCO_ORIGEM_IDENTIFICACAO_ENUM else None


def _normalize_origem_pair(banco, id_registro):
    banco_n = _normalize_banco_origem(banco)
    id_n = _none_if_blank(id_registro)

    # If only one side is present, null out BOTH to satisfy the check constraint
    if (banco_n is None) != (id_n is None):
        return (None, None)

    return (banco_n, id_n)


def load_parquet_file(
    conn: psycopg.Connection,
    file_path: Path,
    *,
    batch_size: int,
    strict_identificador: bool,
    dry_run: bool = False,
) -> dict[str, int]:
    if pq is None:  # pragma: no cover
        raise RuntimeError(
            "pyarrow não está instalado. Instale com: pip install .[loader]"
        ) from _PYARROW_IMPORT_ERROR

    if not file_path.exists():
        raise FileNotFoundError(str(file_path))

    pf = pq.ParquetFile(file_path)
    _validate_columns(file_path, pf.schema.names)

    rows_copiadas = 0
    rows_ignoradas = 0

    # No dry-run tudo roda normalmente (inclusive as constraints) e a
    # transação é desfeita no fim do bloco.
    with conn.transaction(force_rollback=dry_run):
        cur = conn.cursor()

        cur.execute(
            f"""
            CREATE TEMP TABLE {TEMP_TABLE} (
                id_pessoa BIGINT NOT NULL,
                tipo_evento TEXT NOT NULL,
                metodo_identificacao monitoramento.metodo_identificacao_enum NOT NULL,
                data_identificacao DATE NOT NULL,
                tipo_identificador TEXT NOT NULL,
                valor_identificador TEXT NOT NULL,
                banco_origem_identificacao monitoramento.banco_origem_identificacao_enum,
                id_registro_identificacao TEXT,
                gera_alerta BOOLEAN DEFAULT FALSE
            ) ON COMMIT DROP;
            """
        )

        with cur.copy(
            f"COPY {TEMP_TABLE} (id_pessoa, tipo_evento, metodo_identificacao, data_identificacao, tipo_identificador, valor_identificador, banco_origem_identificacao, id_registro_identificacao, gera_alerta) FROM STDIN"
        ) as copy:
            for batch in pf.iter_batches(batch_size=batch_size, columns=COLUMNS):
                cols = [batch.column(i).to_pylist() for i in range(batch.num_columns)]
                for (
                    id_pessoa,
                    tipo_evento,
                    metodo_identificacao,
                    data_identificacao,
                    tipo_identificador,
                    valor_identificador,
                    banco_origem_identificacao,
                    id_registro_identificacao,
                    gera_alerta,
                ) in zip(*cols):
                    if id_pessoa is None:
                        continue

                    if tipo_identificador in {"cpf", "cns"}:
                        # Remover caracteres não numéricos
                        valor_identificador = "".join(
                            ch for ch in str(valor_identificador) if ch.isdigit()
                        )
                        # Rede de segurança para parquets gerados antes da
                        # correção no export: CPF que perdeu o zero à
                        # esquerda não casa com a consulta da API.
                        if tipo_identificador == "cpf" and (
                            1 <= len(valor_identificador) <= 11
                        ):
                            valor_identificador = valor_identificador.zfill(11)
                        banco_n, idreg_n = _normalize_origem_pair(
                            banco_origem_identificacao, id_registro_identificacao
                        )

                        copy.write_row(
                            (
                                int(id_pessoa),
                                str(tipo_evento),
                                str(metodo_identificacao),
                                _normalize_dt(data_identificacao),
                                str(tipo_identificador),
                                str(valor_identificador),
                                banco_n,
                                idreg_n,
                                gera_alerta,
                            )
                        )
                        rows_copiadas += 1
                    else:
                        rows_ignoradas += 1

        cur.execute(
            f"""
            INSERT INTO monitoramento.individuo (id)
            SELECT DISTINCT id_pessoa
            FROM {TEMP_TABLE}
            ON CONFLICT (id) DO NOTHING;
            """
        )
        individuos_inseridos = max(cur.rowcount, 0)

        cur.execute(
            f"""
            INSERT INTO monitoramento.individuo_identificador
                (individuo_id, tipo_identificador, valor_identificador)
            SELECT DISTINCT id_pessoa, tipo_identificador, valor_identificador
            FROM {TEMP_TABLE}
            ON CONFLICT (tipo_identificador, valor_identificador) DO NOTHING;
            """
        )
        identificadores_inseridos = max(cur.rowcount, 0)

        cur.execute(
            f"""
            SELECT
                s.tipo_identificador,
                s.valor_identificador,
                s.id_pessoa AS id_pessoa_novo,
                ii.individuo_id AS id_pessoa_existente
            FROM {TEMP_TABLE} s
            JOIN monitoramento.individuo_identificador ii
              ON ii.tipo_identificador = s.tipo_identificador
             AND ii.valor_identificador = s.valor_identificador
            WHERE ii.individuo_id <> s.id_pessoa
            LIMIT 5;
            """
        )
        conflitos = cur.fetchall()
        if conflitos:
            linhas = [
                f"- {t}={v}: novo={novo} existente={existente}"
                for (t, v, novo, existente) in conflitos
            ]
            msg = (
                "Conflito de identificador: o mesmo (tipo_identificador, valor_identificador) apareceu com id_pessoa diferente.\n"
                + "\n".join(linhas)
            )

            if strict_identificador:
                raise RuntimeError(msg)

            print(msg)

        # Diagnóstico: eventos que já estão no banco sem alerta, mas que o
        # parquet diz que deveriam alertar. Precisa ser medido antes do
        # upsert, que é justamente o que vai corrigi-los.
        cur.execute(
            f"""
            -- DISTINCT nos dois: a staging tem uma linha por identificador
            -- (cpf e cns), então cada evento aparece mais de uma vez no join.
            SELECT
                count(DISTINCT ie.id)           FILTER (WHERE NOT ie.gera_alerta AND s.gera_alerta) AS eventos,
                count(DISTINCT ie.individuo_id) FILTER (WHERE NOT ie.gera_alerta AND s.gera_alerta) AS pessoas
            FROM monitoramento.individuo_evento ie
            JOIN {TEMP_TABLE} s
              ON s.id_pessoa           = ie.individuo_id
             AND s.tipo_evento         = ie.tipo_evento
             AND s.metodo_identificacao = ie.metodo_identificacao
             AND s.banco_origem_identificacao IS NOT DISTINCT FROM ie.banco_origem_identificacao
             AND s.id_registro_identificacao  IS NOT DISTINCT FROM ie.id_registro_identificacao;
            """
        )
        alertas_corrigidos, pessoas_alerta_corrigidas = cur.fetchone()

        # Upsert em dois ramos, um por índice único parcial: V4 cobre as
        # linhas com origem preenchida, V9 as de origem nula.
        cur.execute(
            f"""
            WITH origem AS (
                SELECT
                    id_pessoa,
                    tipo_evento,
                    metodo_identificacao,
                    max(data_identificacao) AS data_identificacao,
                    banco_origem_identificacao,
                    id_registro_identificacao,
                    bool_or(gera_alerta)    AS gera_alerta
                FROM {TEMP_TABLE}
                WHERE banco_origem_identificacao IS NOT NULL
                  AND id_registro_identificacao  IS NOT NULL
                GROUP BY id_pessoa, tipo_evento, metodo_identificacao,
                         banco_origem_identificacao, id_registro_identificacao
            ), upsert AS (
                INSERT INTO monitoramento.individuo_evento AS ie
                    (individuo_id, tipo_evento, metodo_identificacao, data_identificacao,
                     banco_origem_identificacao, id_registro_identificacao, gera_alerta)
                SELECT * FROM origem
                ON CONFLICT (individuo_id, tipo_evento, metodo_identificacao,
                             banco_origem_identificacao, id_registro_identificacao)
                    WHERE id_registro_identificacao  IS NOT NULL
                      AND banco_origem_identificacao IS NOT NULL
                DO UPDATE SET
                    gera_alerta        = EXCLUDED.gera_alerta,
                    data_identificacao = GREATEST(ie.data_identificacao, EXCLUDED.data_identificacao)
                RETURNING (xmax = 0) AS inserido
            )
            SELECT
                count(*) FILTER (WHERE inserido)     AS inseridos,
                count(*) FILTER (WHERE NOT inserido) AS atualizados
            FROM upsert;
            """
        )
        inseridos_origem, atualizados_origem = cur.fetchone()

        cur.execute(
            f"""
            WITH sem_origem AS (
                SELECT
                    id_pessoa,
                    tipo_evento,
                    metodo_identificacao,
                    max(data_identificacao) AS data_identificacao,
                    bool_or(gera_alerta)    AS gera_alerta
                FROM {TEMP_TABLE}
                WHERE banco_origem_identificacao IS NULL
                   OR id_registro_identificacao  IS NULL
                GROUP BY id_pessoa, tipo_evento, metodo_identificacao
            ), upsert AS (
                INSERT INTO monitoramento.individuo_evento AS ie
                    (individuo_id, tipo_evento, metodo_identificacao, data_identificacao,
                     banco_origem_identificacao, id_registro_identificacao, gera_alerta)
                SELECT
                    id_pessoa,
                    tipo_evento,
                    metodo_identificacao,
                    data_identificacao,
                    NULL::monitoramento.banco_origem_identificacao_enum,
                    NULL::text,
                    gera_alerta
                FROM sem_origem
                ON CONFLICT (individuo_id, tipo_evento, metodo_identificacao)
                    WHERE id_registro_identificacao  IS NULL
                      AND banco_origem_identificacao IS NULL
                DO UPDATE SET
                    gera_alerta        = EXCLUDED.gera_alerta,
                    data_identificacao = GREATEST(ie.data_identificacao, EXCLUDED.data_identificacao)
                RETURNING (xmax = 0) AS inserido
            )
            SELECT
                count(*) FILTER (WHERE inserido)     AS inseridos,
                count(*) FILTER (WHERE NOT inserido) AS atualizados
            FROM upsert;
            """
        )
        inseridos_sem_origem, atualizados_sem_origem = cur.fetchone()

        eventos_inseridos = inseridos_origem + inseridos_sem_origem
        eventos_atualizados = atualizados_origem + atualizados_sem_origem

        # setval não é transacional: no dry-run ele avançaria a sequência
        # contando indivíduos que o rollback vai descartar.
        if not dry_run:
            cur.execute(
                """
                SELECT setval(
                    pg_get_serial_sequence('monitoramento.individuo','id'),
                    GREATEST((SELECT COALESCE(MAX(id),0) FROM monitoramento.individuo), 1),
                    true
                );
                """
            )

    return {
        "rows_copiadas": rows_copiadas,
        "rows_ignoradas": rows_ignoradas,
        "individuos_inseridos": individuos_inseridos,
        "identificadores_inseridos": identificadores_inseridos,
        "eventos_inseridos": eventos_inseridos,
        "eventos_atualizados": eventos_atualizados,
        "alertas_corrigidos": alertas_corrigidos,
        "pessoas_alerta_corrigidas": pessoas_alerta_corrigidas,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Carrega arquivos .parquet (resultados offline) para o banco PostgreSQL da API."
    )
    parser.add_argument(
        "--parquet",
        action="append",
        required=True,
        help="Caminho para um arquivo .parquet ou uma pasta contendo .parquet (pode repetir).",
    )
    parser.add_argument(
        "--database-url",
        default=os.getenv("DATABASE_URL", ""),
        help="URL do banco (default: env DATABASE_URL).",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=5000,
        help="Quantidade de linhas por batch ao ler o parquet.",
    )
    parser.add_argument(
        "--strict-identificador",
        action="store_true",
        help="Falha quando houver conflito de identificador já existente com id_pessoa diferente.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Executa a carga inteira e desfaz no fim, apenas relatando o que mudaria.",
    )

    args = parser.parse_args()

    if not args.database_url:
        raise SystemExit(
            "DATABASE_URL não informado (use --database-url ou env DATABASE_URL)."
        )

    parquet_files: list[Path] = []
    for p in args.parquet:
        parquet_files.extend(_iter_parquet_files(p))

    parquet_files = [p for p in parquet_files if p.exists()]
    if not parquet_files:
        raise SystemExit("Nenhum arquivo .parquet encontrado.")

    dsn = _dsn_for_psycopg(args.database_url)

    if args.dry_run:
        print("DRY-RUN: nenhuma alteração será persistida.")

    with psycopg.connect(dsn) as conn:
        total: dict[str, int] = {}

        for fp in parquet_files:
            res = load_parquet_file(
                conn,
                fp,
                batch_size=args.batch_size,
                strict_identificador=args.strict_identificador,
                dry_run=args.dry_run,
            )

            print(f"OK: {fp} -> {res}")
            for k, v in res.items():
                total[k] = total.get(k, 0) + v

        print(f"TOTAL: {total}")

        if total.get("alertas_corrigidos"):
            print(
                f"ATENÇÃO: {total['alertas_corrigidos']} evento(s) já no banco estavam com "
                f"gera_alerta=false e o parquet indica alerta "
                f"({total['pessoas_alerta_corrigidas']} pessoa(s), contadas por arquivo)."
            )


if __name__ == "__main__":
    main()
