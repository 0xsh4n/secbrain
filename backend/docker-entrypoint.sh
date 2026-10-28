#!/usr/bin/env bash
# Entrypoint: wait for the database, run migrations, bootstrap, then exec CMD.
set -euo pipefail

echo "[entrypoint] running database migrations..."
alembic upgrade head

if [ "${SECBRAIN_BOOTSTRAP_ON_START:-true}" = "true" ]; then
  echo "[entrypoint] bootstrapping admin + default collections (idempotent)..."
  python -m app.cli bootstrap || true
fi

if [ "${SECBRAIN_SEED_SAMPLES_ON_START:-false}" = "true" ]; then
  echo "[entrypoint] seeding sample documents..."
  python -m app.cli seed-samples || true
fi

echo "[entrypoint] starting: $*"
exec "$@"
