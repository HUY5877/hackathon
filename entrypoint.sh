#!/bin/sh
set -e

# 1. 先同步（把空数据库升级到你本地已有的最新版本）
echo "Running database migrations..."
alembic upgrade head

# 2. 再检测（此时数据库和本地已经对齐了，可以安全地检测有没有新写进代码的 Model 变动了）
echo "Generating new migrations if any..."
alembic revision --autogenerate -m "auto"

# 3. 再次同步（如果有新生成的，立刻应用到数据库）
alembic upgrade head

echo "Starting server..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
