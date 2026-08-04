#!/bin/sh
set -e

python vercel_migrations.py

echo "Starting server..."
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-80}"
