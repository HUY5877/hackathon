#!/bin/sh
set -e

echo "Running database migrations..."
alembic upgrade head

echo "Generating new migrations from current models..."
alembic revision --autogenerate -m "auto"

echo "Applying generated migrations..."
alembic upgrade head

echo "Starting server..."
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-80}"
