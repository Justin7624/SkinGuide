#!/usr/bin/env bash
set -euo pipefail

cd /app

# Run migrations
alembic -c alembic.ini upgrade head

# Start API
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
