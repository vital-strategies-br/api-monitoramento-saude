FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml README.md ./
RUN pip install --upgrade pip \
    && pip install ".[loader]"

COPY app ./app
COPY scripts ./scripts

RUN chmod 755 ./scripts/start.sh

EXPOSE 8000

ENV GUNICORN_WORKERS=2

CMD ["sh", "./scripts/start.sh"]
