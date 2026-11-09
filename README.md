# api-monitoramento-saude

API for querying relations between identifiers and health events.

## Run with Docker Compose

```bash
cp .env.example .env   # then replace every <...> placeholder
docker compose up --build
```

`.env.example` lists every setting with the production values from the
specification; lines marked `dev:` give the training server value. Keep real
keys and secrets only in `.env`, which is gitignored.

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

## Telemetry events

`POST /api/v1/telemetria/eventos` receives dashboard events from the alert plugin
backend (Pitang), as defined in section 8 of the Alert Plugin Final Specification.
It uses the same `X-API-Key` + HMAC authentication as the query API. Apply Flyway
migration V12 before running this version.

Events are stored in `monitoramento.telemetria_evento`: the full event as received in
`payload`, plus `evento_id`, `evento` and `alerta_id` columns that enforce the contract,
and the `internal_id` / `created_by` / `created_on` / `updated_by` / `updated_on` audit
columns. `created_by` is the SHA-256 of the caller's API key, never the key itself.

### Responses

Every event in a batch lands in exactly one bucket, so
`aceitos + duplicados + len(rejeitados)` always equals the number of events sent.

| Situation | Result |
|---|---|
| Valid event, new `evento_id` | stored, counted in `aceitos` |
| `evento_id` already received (same call or earlier) | ignored, first one wins, counted in `duplicados` |
| Same `evento_id` with different content | as above, plus a `telemetria_duplicado_divergente` warning log (field names only) |
| Second `alerta_encerrado` for the same `alerta_id` | `rejeitados`, `campo: alerta_id` |
| Not an object, missing/invalid `evento_id` or `alerta_id`, unknown `evento`, or one of `alerta_tipo`, `alerta_origem`, `atualizacao_base_id`, `paciente_id` present | `rejeitados`, one item per event; `evento_id` is `null` when the event has no string `evento_id` |
| Unknown `alerta_id` | accepted (spec 8.6) |

Errors always carry `detail` as a single string, in Portuguese:

| Call | Status | `detail` |
|---|---|---|
| `{"eventos": []}` | 422 | `Lote vazio: informe ao menos 1 evento` |
| `eventos` missing / not a list / malformed JSON | 422 | e.g. `eventos: campo obrigatório ausente`, `JSON malformado` |
| More than `TELEMETRY_MAX_BATCH_SIZE` events | 413 | `Lote acima do limite: envie no máximo 200 eventos por chamada` |
| Body larger than `MAX_REQUEST_BODY_BYTES` | 413 | `Corpo da requisição acima do limite: envie no máximo 1048576 bytes por chamada` |
| Rate limit exceeded | 429 | `Limite de requisições excedido: tente novamente em N segundos` (+ `Retry-After`) |
| Database failure | 500 | `Erro interno` (nothing from the batch is stored) |

### Limits and configuration

All limits are environment variables (defaults in `app/core/config.py` and `docker-compose.yml`):

| Variable | Default | Applies to |
|---|---|---|
| `TELEMETRY_MAX_BATCH_SIZE` | `200` | events per telemetry call (spec value; change only together with Pitang) |
| `MAX_REQUEST_BODY_BYTES` | `1048576` (1 MiB) | body of every authenticated route, checked before auth reads it |
| `RATE_LIMIT_ENABLED` | `false` | turns the per-IP rate limit on |
| `RATE_LIMIT_REQUESTS` | `120` | requests per window per client IP |
| `RATE_LIMIT_WINDOW_SECONDS` | `60` | window length |
| `RATE_LIMIT_EXEMPT_IPS` | empty | comma-separated IPs never limited (the Pitang backend outbound IP) |
| `FORWARDED_ALLOW_IPS` | `127.0.0.1` | proxies trusted for `X-Forwarded-For` (read by gunicorn) |

The rate limit covers every `/api/v1` route, including the query API called by the
plugin from the health units. Counters live in each worker's memory, so the effective
ceiling is `RATE_LIMIT_REQUESTS x GUNICORN_WORKERS`. Behind a reverse proxy, list the
proxy in `FORWARDED_ALLOW_IPS`, otherwise every client appears as the proxy's IP and
shares one counter. A proxy in front of the API also needs its own body limit at least
as large as `MAX_REQUEST_BODY_BYTES` (nginx defaults to 1 MiB with `client_max_body_size`).

Go-live order for the rate limit (spec 8.6 and 10.2):
1. Pitang sends the backend's outbound IP; set it in `RATE_LIMIT_EXEMPT_IPS`.
2. Confirm `FORWARDED_ALLOW_IPS` resolves real client IPs in that environment.
3. Set `RATE_LIMIT_ENABLED=true`.
4. Only then start the historical backfill.

### What Pitang needs to change

1. **Split by size, not only by count.** A call must have at most 200 events **and** at
   most 1,048,576 bytes of body. A 413 means one of the two was exceeded; `detail` says
   which. Split the batch (e.g. in half) and resend the halves with the same `evento_id`
   values. If a single event alone exceeds the byte limit, it is a client bug: fix it,
   do not retry.
2. **Send the body as plain JSON.** Compression (`Content-Encoding: gzip`) is not
   supported; the HMAC is computed over the bytes exactly as sent.
3. **Handle 429.** Wait the seconds in `Retry-After`, then resend the same batch with
   the same `evento_id` values. Once the backend IP is exempt this should not happen
   for telemetry.
4. **Send the backend's outbound IP** to Vital before the backfill (step 1 above).
5. **Read `detail` as a string** for every 4xx error.
6. **Treat `rejeitados` as final for that event** until it is fixed: resend only the
   corrected events. A rejection with `campo: alerta_id` and `mensagem:
   alerta_encerrado já registrado para este alerta_id` means the alert was already
   closed; do not resend it.
7. **Never reuse an `evento_id` for different content.** It is ignored and logged.
8. **Do not send** `alerta_tipo`, `alerta_origem`, `atualizacao_base_id` or
   `paciente_id`; events carrying them are rejected (spec CE-11).

## Tests

```bash
pip install .[dev]
pytest
```
