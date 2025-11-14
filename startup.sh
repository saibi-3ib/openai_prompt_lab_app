#!/usr/bin/env bash
set -euo pipefail

# Wait for DATABASE_URL to be connectable (retry loop)
RETRIES=30
SLEEP_SECONDS=3

echo "startup.sh: Waiting for database to be available..."
i=0
while [ $i -lt $RETRIES ]; do
  python - <<'PY' >/dev/null 2>&1 && rc=$? || rc=$?
import os
from sqlalchemy import create_engine
try:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise SystemExit(2)
    engine = create_engine(url)
    conn = engine.connect()
    conn.close()
    raise SystemExit(0)
except Exception:
    raise SystemExit(1)
PY
  if [ $rc -eq 0 ]; then
    echo "startup.sh: Database reachable."
    break
  fi
  i=$((i+1))
  echo "startup.sh: DB not ready yet (attempt ${i}/${RETRIES}), sleeping ${SLEEP_SECONDS}s..."
  sleep $SLEEP_SECONDS
done

if [ $i -ge $RETRIES ]; then
  echo "startup.sh: Database did not become ready after ${RETRIES} attempts. Exiting." >&2
  exit 1
fi

# Run DB migrations (alembic)
echo "startup.sh: Running alembic upgrade head..."
export FLASK_APP=run.py
alembic -c alembic.ini upgrade head

# Start the web server
echo "startup.sh: Starting Gunicorn..."
exec gunicorn wsgi:app --bind 0.0.0.0:${PORT:-10000} --workers ${WEB_CONCURRENCY:-2}