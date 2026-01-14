#!/bin/sh
set -eu

: "${GUNICORN_WORKERS:=2}"
: "${BIND:=0.0.0.0:8000}"

exec gunicorn \
  -k uvicorn.workers.UvicornWorker \
  -w "$GUNICORN_WORKERS" \
  -b "$BIND" \
  app.main:app
