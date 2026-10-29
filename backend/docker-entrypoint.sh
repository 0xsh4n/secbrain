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

# Download the Nyx (Piper) voice model if TTS is enabled and it's missing.
if [ "${SECBRAIN_TTS_PROVIDER:-piper}" = "piper" ] && [ "${SECBRAIN_DOWNLOAD_VOICE_ON_START:-true}" = "true" ]; then
  echo "[entrypoint] ensuring Piper voice model is present..."
  python -m app.cli download-voice || echo "[entrypoint] voice download skipped (TTS will 503; UI falls back to browser speech)"
fi

echo "[entrypoint] starting: $*"
exec "$@"
