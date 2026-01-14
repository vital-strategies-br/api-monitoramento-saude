FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml README.md ./
COPY app ./app
COPY scripts ./scripts

RUN chmod 755 ./scripts/start.sh

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir ".[loader]"

EXPOSE 8000

# default: 2, can override with -e GUNICORN_WORKERS=...
ENV GUNICORN_WORKERS=2

CMD ["sh", "./scripts/start.sh"]

