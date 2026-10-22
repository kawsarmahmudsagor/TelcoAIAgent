#!/bin/sh
set -e

case "$1" in
  api)
    alembic upgrade head
    exec uvicorn app.main:app --host 0.0.0.0 --port 8000
    ;;
  agent-worker)
    exec python -m app.agent.worker start
    ;;
  scheduler)
    exec python -m app.scheduler.worker
    ;;
  seed)
    alembic upgrade head
    exec python -m app.data.seed_all
    ;;
  *)
    exec "$@"
    ;;
esac
