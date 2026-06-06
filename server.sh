#!/bin/bash
set -e

DIR="$(cd "$(dirname "$0")" && pwd)"
PID_FILE="/tmp/screener.pid"

_start() {
  if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
    echo "Already running (PID $(cat "$PID_FILE"))."
    exit 1
  fi

  set -a
  source "$DIR/config.env"
  set +a

  uv run gunicorn -w 2 -b "0.0.0.0:${PORT:-5000}" app:app \
    --daemon \
    --pid "$PID_FILE" \
    --timeout 180 \
    --access-logfile /tmp/screener-access.log \
    --error-logfile /tmp/screener-error.log

  for i in 1 2 3 4 5; do
    [ -f "$PID_FILE" ] && break
    sleep 0.5
  done
  echo "Started (PID: $(cat "$PID_FILE"))."
}

_stop() {
  # Kill PID-file process if present
  if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if kill "$PID" 2>/dev/null; then
      echo "Stopped PID $PID."
    else
      echo "PID $PID already gone."
    fi
    rm -f "$PID_FILE"
  fi

  # Sweep any stray gunicorn workers (orphans, outside-server.sh starts, crashes)
  if pkill -f "gunicorn.*app:app" 2>/dev/null; then
    echo "Swept stray gunicorn processes."
  fi

  # Wait up to 5 s for processes to exit before returning
  for i in 1 2 3 4 5; do
    pgrep -f "gunicorn.*app:app" > /dev/null 2>&1 || break
    sleep 1
  done
}

case "${1:-}" in
  start)   _start ;;
  stop)    _stop ;;
  restart) _stop; sleep 1; _start ;;
  status)
    if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
      echo "Running (PID $(cat "$PID_FILE"))."
    else
      echo "Stopped."
    fi
    ;;
  *)
    echo "Usage: $0 {start|stop|restart|status}"
    exit 1
    ;;
esac
