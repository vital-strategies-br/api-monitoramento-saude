"""Loader for result files (.parquet) into PostgreSQL.

The parquet must contain the columns:
- id_pessoa
- tipo_evento
- data_identificacao
- tipo_identificador
- valor_identificador

This script populates the tables:
- monitoramento.individuo (id = id_pessoa)
- monitoramento.individuo_identificador
- monitoramento.individuo_evento

The event load is an idempotent upsert: the parquet is the source of
truth for gera_alerta, and data_identificacao only moves forward. Requires
migration V9, which creates the unique index for rows without a source. The
final report shows how many events already in the database had no alert
even though the parquet indicates one.

To read parquet, install the extra:
    pip install .[loader]

Usage:
    python scripts/load_parquet.py --parquet /path/file.parquet
    python scripts/load_parquet.py --parquet /path/folder_with_parquets
    python scripts/load_parquet.py --parquet /path/file.parquet --dry-run

By default, the script uses the DATABASE_URL environment variable.
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

IDENTIFICATION_SOURCE_DATABASE_ENUM = set(["e-SUS APS", "Sinan - Violências"])

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
        raise TypeError("data_identificacao cannot be None")

    if isinstance(value, date) and not isinstance(value, datetime):
        return value

    if isinstance(value, datetime):
        return value.date()

    if isinstance(value, (int, float)):
        return datetime.utcfromtimestamp(value).date()

    if isinstance(value, str):
        s = value.strip()
        # accepts a full ISO timestamp or just a date
        return date.fromisoformat(s[:10])

    raise TypeError(f"Invalid type for data_identificacao: {type(value)!r}")


def _validate_columns(file_path: Path, available: Iterable[str]) -> None:
    missing = set(COLUMNS).difference(set(available))
    if missing:
        cols = ", ".join(sorted(missing))
        raise ValueError(
            f"Parquet '{file_path}' is missing required columns: {cols}"
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


def _normalize_source_database(v):
    s = _none_if_blank(v)
    if s is None:
        return None
    # normalize common whitespace issues
    s = " ".join(s.split())
    return s if s in IDENTIFICATION_SOURCE_DATABASE_ENUM else None


def _normalize_source_pair(database, record_id):
    database_n = _normalize_source_database(database)
    id_n = _none_if_blank(record_id)

    # If only one side is present, null out BOTH to satisfy the check constraint
    if (database_n is None) != (id_n is None):
        return (None, None)

    return (database_n, id_n)


def load_parquet_file(
    conn: psycopg.Connection,
    file_path: Path,
    *,
    batch_size: int,
    strict_identifier: bool,
    dry_run: bool = False,
) -> dict[str, int]:
    if pq is None:  # pragma: no cover
        raise RuntimeError(
            "pyarrow is not installed. Install it with: pip install .[loader]"
        ) from _PYARROW_IMPORT_ERROR

    if not file_path.exists():
        raise FileNotFoundError(str(file_path))

    pf = pq.ParquetFile(file_path)
    _validate_columns(file_path, pf.schema.names)

    rows_copied = 0
    rows_skipped = 0

    # In dry-run everything runs normally (including the constraints) and the
    # transaction is rolled back at the end of the block.
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
                        # Remove non-numeric characters
                        valor_identificador = "".join(
                            ch for ch in str(valor_identificador) if ch.isdigit()
                        )
                        # Safety net for parquets generated before the
                        # export fix: a CPF that lost its leading zero
                        # does not match the API lookup.
                        if tipo_identificador == "cpf" and (
                            1 <= len(valor_identificador) <= 11
                        ):
                            valor_identificador = valor_identificador.zfill(11)
                        database_n, record_id_n = _normalize_source_pair(
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
                                database_n,
                                record_id_n,
                                gera_alerta,
                            )
                        )
                        rows_copied += 1
                    else:
                        rows_skipped += 1

        cur.execute(
            f"""
            INSERT INTO monitoramento.individuo (id)
            SELECT DISTINCT id_pessoa
            FROM {TEMP_TABLE}
            ON CONFLICT (id) DO NOTHING;
            """
        )
        individuals_inserted = max(cur.rowcount, 0)

        cur.execute(
            f"""
            INSERT INTO monitoramento.individuo_identificador
                (individuo_id, tipo_identificador, valor_identificador)
            SELECT DISTINCT id_pessoa, tipo_identificador, valor_identificador
            FROM {TEMP_TABLE}
            ON CONFLICT (tipo_identificador, valor_identificador) DO NOTHING;
            """
        )
        identifiers_inserted = max(cur.rowcount, 0)

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
        conflicts = cur.fetchall()
        if conflicts:
            lines = [
                f"- {t}={v}: new={new} existing={existing}"
                for (t, v, new, existing) in conflicts
            ]
            msg = (
                "Identifier conflict: the same (tipo_identificador, valor_identificador) appeared with a different id_pessoa.\n"
                + "\n".join(lines)
            )

            if strict_identifier:
                raise RuntimeError(msg)

            print(msg)

        # Diagnostic: events already in the database without an alert that the
        # parquet says should alert. Must be measured before the
        # upsert, which is exactly what will fix them.
        cur.execute(
            f"""
            -- DISTINCT on both: staging has one row per identifier
            -- (cpf and cns), so each event appears more than once in the join.
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
        alerts_fixed, people_alerts_fixed = cur.fetchone()

        # Upsert in two branches, one per partial unique index: V4 covers
        # rows with a source set, V9 those with a null source.
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
        inserted_with_source, updated_with_source = cur.fetchone()

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
        inserted_without_source, updated_without_source = cur.fetchone()

        events_inserted = inserted_with_source + inserted_without_source
        events_updated = updated_with_source + updated_without_source

        # setval is not transactional: in dry-run it would advance the sequence
        # counting individuals that the rollback will discard.
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
        "rows_copiadas": rows_copied,
        "rows_ignoradas": rows_skipped,
        "individuos_inseridos": individuals_inserted,
        "identificadores_inseridos": identifiers_inserted,
        "eventos_inseridos": events_inserted,
        "eventos_atualizados": events_updated,
        "alertas_corrigidos": alerts_fixed,
        "pessoas_alerta_corrigidas": people_alerts_fixed,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Loads .parquet files (offline results) into the API's PostgreSQL database."
    )
    parser.add_argument(
        "--parquet",
        action="append",
        required=True,
        help="Path to a .parquet file or a folder containing .parquet files (repeatable).",
    )
    parser.add_argument(
        "--database-url",
        default=os.getenv("DATABASE_URL", ""),
        help="Database URL (default: env DATABASE_URL).",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=5000,
        help="Number of rows per batch when reading the parquet.",
    )
    parser.add_argument(
        "--strict-identificador",
        action="store_true",
        help="Fail when an existing identifier conflicts with a different id_pessoa.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run the full load and roll back at the end, only reporting what would change.",
    )

    args = parser.parse_args()

    if not args.database_url:
        raise SystemExit(
            "DATABASE_URL not provided (use --database-url or env DATABASE_URL)."
        )

    parquet_files: list[Path] = []
    for p in args.parquet:
        parquet_files.extend(_iter_parquet_files(p))

    parquet_files = [p for p in parquet_files if p.exists()]
    if not parquet_files:
        raise SystemExit("No .parquet files found.")

    dsn = _dsn_for_psycopg(args.database_url)

    if args.dry_run:
        print("DRY-RUN: no changes will be persisted.")

    with psycopg.connect(dsn) as conn:
        total: dict[str, int] = {}

        for fp in parquet_files:
            res = load_parquet_file(
                conn,
                fp,
                batch_size=args.batch_size,
                strict_identifier=args.strict_identificador,
                dry_run=args.dry_run,
            )

            print(f"OK: {fp} -> {res}")
            for k, v in res.items():
                total[k] = total.get(k, 0) + v

        print(f"TOTAL: {total}")

        if total.get("alertas_corrigidos"):
            print(
                f"WARNING: {total['alertas_corrigidos']} event(s) already in the database had "
                f"gera_alerta=false while the parquet indicates an alert "
                f"({total['pessoas_alerta_corrigidas']} person(s), counted per file)."
            )


if __name__ == "__main__":
    main()
