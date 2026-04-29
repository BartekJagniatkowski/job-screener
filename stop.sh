#!/bin/bash
DIR="$(cd "$(dirname "$0")" && pwd)"
PID_FILE="$DIR/data/app.pid"

if [ -f "$PID_FILE" ]; then
  PID=$(cat "$PID_FILE")
  if kill "$PID" 2>/dev/null; then
    echo "Job Screener zatrzymany (PID $PID)."
  else
    echo "Proces $PID już nie działał."
  fi
  rm -f "$PID_FILE"
else
  echo "Aplikacja nie działa (brak pliku PID)."
fi
