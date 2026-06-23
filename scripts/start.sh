#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="${1:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8000}"
LOG_FILE="${LOG_FILE:-/tmp/wordstat_app.log}"
PID_FILE="${PID_FILE:-/tmp/wordstat_app.pid}"

cd "$PROJECT_DIR"

if [[ ! -d .venv ]]; then
  python3 -m venv --copies .venv
fi

. .venv/bin/activate
pip install -r requirements.txt

if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
  echo "Application is already running with PID $(cat "$PID_FILE")."
  exit 0
fi

nohup python -m uvicorn --app-dir "$PROJECT_DIR" app.main:app --host "$HOST" --port "$PORT" > "$LOG_FILE" 2>&1 &
echo $! > "$PID_FILE"

echo "Application started: http://${HOST}:${PORT}"
echo "PID file: $PID_FILE"
echo "Log file: $LOG_FILE"
