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

Para ler parquet, instale o extra:
    pip install .[loader]

Uso:
    python scripts/load_parquet.py --parquet /caminho/arquivo.parquet
    python scripts/load_parquet.py --parquet /caminho/pasta_com_parquets

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


def load_parquet_file(
    conn: psycopg.Connection,
    file_path: Path,
    *,
    batch_size: int,
    strict_identificador: bool,
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

    with conn.transaction():
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
                id_registro_identificacao TEXT
            ) ON COMMIT DROP;
            """
        )

        with cur.copy(
            f"COPY {TEMP_TABLE} (id_pessoa, tipo_evento, metodo_identificacao, data_identificacao, tipo_identificador, valor_identificador, banco_origem_identificacao, id_registro_identificacao) FROM STDIN"
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
                ) in zip(*cols):
                    if id_pessoa is None:
                        continue

                    if tipo_identificador in {"cpf", "cns"}:
                        # Remover caracteres não numéricos
                        valor_identificador = "".join(
                            ch for ch in str(valor_identificador) if ch.isdigit()
                        )

                    copy.write_row(
                        (
                            int(id_pessoa),
                            str(tipo_evento),
                            str(metodo_identificacao),
                            _normalize_dt(data_identificacao),
                            str(tipo_identificador),
                            str(valor_identificador),
                            str(banco_origem_identificacao)
                            if banco_origem_identificacao
                            in BANCO_ORIGEM_IDENTIFICACAO_ENUM
                            else None,
                            str(id_registro_identificacao)
                            if id_registro_identificacao is not None
                            else None,
                        )
                    )
                    rows_copiadas += 1

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

        cur.execute(
            f"""
            INSERT INTO monitoramento.individuo_evento
                (individuo_id, tipo_evento, metodo_identificacao, data_identificacao, banco_origem_identificacao, id_registro_identificacao)
            SELECT id_pessoa, tipo_evento, metodo_identificacao, data_identificacao, banco_origem_identificacao, id_registro_identificacao
            FROM {TEMP_TABLE}
            ON CONFLICT DO NOTHING;
            """
        )
        eventos_inseridos = max(cur.rowcount, 0)

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
        "individuos_inseridos": individuos_inseridos,
        "identificadores_inseridos": identificadores_inseridos,
        "eventos_inseridos": eventos_inseridos,
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

    with psycopg.connect(dsn) as conn:
        total = {
            "rows_copiadas": 0,
            "individuos_inseridos": 0,
            "identificadores_inseridos": 0,
            "eventos_inseridos": 0,
        }

        for fp in parquet_files:
            res = load_parquet_file(
                conn,
                fp,
                batch_size=args.batch_size,
                strict_identificador=args.strict_identificador,
            )

            print(f"OK: {fp} -> {res}")
            for k, v in res.items():
                total[k] += v

        print(f"TOTAL: {total}")


if __name__ == "__main__":
    main()
