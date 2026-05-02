#!/bin/bash
set -e

DIR="$(cd "$(dirname "$0")" && pwd)"
PID_FILE="/tmp/screener.pid"

_start() {
  if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
    echo "Serwer już działa (PID $(cat "$PID_FILE"))."
    exit 1
  fi

  set -a
  source "$DIR/config.env"
  set +a

  uv run gunicorn -w 2 -b "0.0.0.0:${PORT:-5000}" app:app \
    --daemon \
    --pid "$PID_FILE" \
    --access-logfile /tmp/screener-access.log \
    --error-logfile /tmp/screener-error.log

  for i in 1 2 3 4 5; do
    [ -f "$PID_FILE" ] && break
    sleep 0.5
  done
  echo "Serwer uruchomiony (PID: $(cat "$PID_FILE"))."
}

_stop() {
  if [ ! -f "$PID_FILE" ]; then
    echo "Aplikacja nie działa (brak pliku PID)."
    return 0
  fi

  PID=$(cat "$PID_FILE")
  if kill "$PID" 2>/dev/null; then
    echo "Serwer zatrzymany (PID $PID)."
  else
    echo "Proces $PID już nie działał."
  fi
  rm -f "$PID_FILE"
}

case "${1:-}" in
  start)   _start ;;
  stop)    _stop ;;
  restart) _stop; sleep 1; _start ;;
  status)
    if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
      echo "Działa (PID $(cat "$PID_FILE"))."
    else
      echo "Zatrzymany."
    fi
    ;;
  *)
    echo "Użycie: $0 {start|stop|restart|status}"
    exit 1
    ;;
esac
