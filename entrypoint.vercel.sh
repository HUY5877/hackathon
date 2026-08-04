#!/bin/sh
set -e

export VERCEL_MIGRATION_READY_FILE="${VERCEL_MIGRATION_READY_FILE:-/tmp/vercel-migrations-ready}"
rm -f "$VERCEL_MIGRATION_READY_FILE"

python vercel_migrations.py &

echo "Starting server..."
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-80}"
