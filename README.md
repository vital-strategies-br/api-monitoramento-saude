# api-monitoramento-saude

API for querying relations between identifiers and health events.

## Run with Docker Compose

```bash
docker compose up --build
```

- API: http://localhost:8000
- Swagger (docs): http://localhost:8000/docs
- Healthcheck: http://localhost:8000/health

`docker-compose.yml` starts:
- PostgreSQL 16
- Flyway (migrations in `db/migration`)
- API (Gunicorn + UvicornWorker)

## Authentication (X-API-Key + HMAC)

Routes that are **not** exempt require the header:
- `X-API-Key`: one of the keys in `API_KEYS` (comma-separated)

When HMAC is enabled (`ENV=prod` or `REQUIRE_HMAC=true`), these are also required:
- `X-Timestamp`: epoch in seconds (or milliseconds)
- `X-Signature`: HMAC-SHA256 (hex)

Signed string:

```
{timestamp}\n{METHOD}\n{PATH}\n{QUERY}\n{sha256(body)}
```

## Generate the parquet

`scripts/exportar_parquet.sql` runs in DuckDB against the linkage database and produces `dados_api.parquet`.

```bash
# production: real data only
duckdb -c ".read scripts/exportar_parquet.sql"

# dev: includes 2 fictitious people for smoke-testing the endpoint
duckdb -c "SET VARIABLE incluir_linhas_teste = true;" -c ".read scripts/exportar_parquet.sql"
```

The list of pilot-unit CNES codes comes from `unidades_piloto.txt`, resolved by
`scripts/conferir_unidades_piloto.sql` (read-only). When the units spreadsheet
changes, run that script and reflect the list in the export.

## Load data from parquet

The `scripts/load_parquet.py` script loads offline results into the database. The loader dependencies are already installed in the image.

The load is an idempotent upsert: the parquet is the source of truth for `gera_alerta`,
and `data_identificacao` only moves forward. Running the same parquet twice does not duplicate anything.
Use `--dry-run` before the real load — it runs everything with the constraints and rolls back
at the end, also reporting how many events already in the database had no alert even though
the parquet indicates one.

### 1. (Recommended) Load via container

Assuming the parquet file is at ```./data/exemplo.parquet``` on the host. 

```bash
sudo docker compose run --rm -v "$(pwd)/data:/data:ro" -e DATABASE_URL='postgresql+psycopg://monitoramento:monitoramento@db:5432/monitoramento_saude' api sh -lc "python scripts/load_parquet.py --parquet /data/exemplo.parquet"
```

### 2. Local execution

First install the loader dependencies:

```bash
pip install .[loader]
```

Then run the script with the database connection string:

```bash
export DATABASE_URL='postgresql+psycopg://monitoramento:monitoramento@localhost:5432/monitoramento_saude'
python scripts/load_parquet.py --parquet /path/resultado.parquet
```


## Alert audit trail

Apply Flyway migration V11 before running this version of the API.
Positive relation responses now include `alerta_id`, a UUID that stays the same
for the same `individuo_evento` across requests. Negative responses have
`alerta_id: null`. Event selection and identification method priority are unchanged.

Example response from `POST /api/v1/relacao/violencia` for a SINAN alert:

```json
{
  "relacionado": true,
  "alerta_id": "3f6c2a1e-8b4d-4c2f-9a7e-1d2b3c4d5e6f",
  "metodo_identificacao": "notificacao_sinan",
  "data_identificacao": "2026-10-28",
  "banco_origem_identificacao": "Sinan - Violências",
  "id_registro_identificacao": "1234567890"
}
```

`alerta_id` identifies the application's alert; `id_registro_identificacao`
identifies the source database record and remains a string. The identification
date uses `YYYY-MM-DD`. When no alert is found, `relacionado` is `false` and
all five other response fields are `null`.

`monitoramento.alerta` identifies the source event. Each positive request creates
an `alerta_resposta` with the endpoint, timestamp and a snapshot of the returned
identification details. `alerta_resposta_identificador` records every distinct,
normalized identifier submitted with that request, including unmatched identifiers;
these records describe the query, not proof that each identifier belongs to the
selected person. Repeated requests create separate response records.

The audit records and positive daily counter commit together before returning
success. A failure returns HTTP 500 and rolls back both. Negative/conflict daily
metrics retain their existing behavior; they do not create alert records.
There is no backfill: historical daily totals cannot identify alerts served.
Audit foreign keys prevent deleting referenced source events or audit records.

Use `scripts/stats_alertas_servidos.sql` for counts and first/last response times
per identifier and alert. Join the response table directly for individual timestamps
and the exact identification details used at the time. Records contain sensitive
identifiers and require the same database access controls as the identifier table.
An audit record means the API prepared a positive response; network delivery and
frontend display require a separate client acknowledgement mechanism.

## Tests

```bash
pip install .[dev]
pytest
```
