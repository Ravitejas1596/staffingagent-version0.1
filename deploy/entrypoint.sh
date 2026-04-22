#!/bin/sh

echo "=== Running database migrations ==="
python -m deploy.db.migrate || echo "WARNING: Migration exited with non-zero code — starting API anyway"

echo "=== Starting API server ==="
exec uvicorn app_platform.api.main:app --host 0.0.0.0 --port 8000
