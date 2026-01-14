# api-monitoramento-saude

API para consulta de relações entre identificadores e eventos de saúde.

## Executar com Docker Compose

```bash
docker compose up --build
```

- API: http://localhost:8000
- Swagger (docs): http://localhost:8000/docs
- Healthcheck: http://localhost:8000/health

O `docker-compose.yml` inicia:
- PostgreSQL 16
- Flyway (migrações em `db/migration`)
- API (Gunicorn + UvicornWorker)

## Autenticação (X-API-Key + HMAC)

As rotas **não** isentas exigem o header:
- `X-API-Key`: uma das chaves em `API_KEYS` (separadas por vírgula)

Quando HMAC estiver habilitado (`ENV=prod` ou `REQUIRE_HMAC=true`), também são exigidos:
- `X-Timestamp`: epoch em segundos (ou milissegundos)
- `X-Signature`: HMAC-SHA256 (hex)

String assinada:

```
{timestamp}\n{METHOD}\n{PATH}\n{QUERY}\n{sha256(body)}
```

## Carregar dados a partir de parquet

O script `scripts/load_parquet.py` carrega resultados offline no banco. As dependências do loader já estão instaladas na imagem.

### 1. (Recomendado) Inclusão via container

Assumindo que o arquivo parquet está no caminho ```./data/exemplo.parquet``` no host. 

```bash
sudo docker compose run --rm -v "$(pwd)/data:/data:ro" -e DATABASE_URL='postgresql+psycopg://monitoramento:monitoramento@db:5432/monitoramento_saude' api sh -lc "python scripts/load_parquet.py --parquet /data/exemplo.parquet"
```

### 2. Execução local

Primeiro instale as dependências do loader:

```bash
pip install .[loader]
```

E execute o script com a string de conexsão do banco:

```bash
export DATABASE_URL='postgresql+psycopg://monitoramento:monitoramento@localhost:5432/monitoramento_saude'
python scripts/load_parquet.py --parquet /caminho/resultado.parquet
```


## Testes

```bash
pip install .[dev]
pytest
```
