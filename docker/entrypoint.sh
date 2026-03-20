#!/bin/sh
set -eu

mkdir -p /app/instance /app/chroma_db /app/static/uploads

flask --app app.py init-db

if [ "${CREATE_ADMIN_ON_BOOT:-true}" = "true" ]; then
  flask --app app.py create-admin || true
fi

if [ "${SEED_ON_BOOT:-false}" = "true" ]; then
  flask --app app.py seed || true
fi

exec gunicorn \
  --bind 0.0.0.0:5000 \
  --workers "${GUNICORN_WORKERS:-2}" \
  --threads "${GUNICORN_THREADS:-4}" \
  --timeout "${GUNICORN_TIMEOUT:-120}" \
  app:app
