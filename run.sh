#!/bin/bash
# Uruchomienie na serwerze jako daemon
set -a
source config.env
set +a

uv run gunicorn -w 2 -b 0.0.0.0:${PORT:-5000} app:app \
  --daemon \
  --pid /tmp/screener.pid \
  --access-logfile /tmp/screener-access.log \
  --error-logfile /tmp/screener-error.log

echo "Serwer uruchomiony (PID: $(cat /tmp/screener.pid))"
