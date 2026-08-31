#!/bin/sh
set -e

# Production only applies migration files that were generated, reviewed, and
# committed during development. Never autogenerate migrations at startup.
echo "Running database migrations..."
alembic upgrade head

echo "Starting server..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
