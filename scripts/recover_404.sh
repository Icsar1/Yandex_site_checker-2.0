#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="${1:-/root/tmp_sk/yandex_site_checker}"
PORT="${2:-8000}"
LOG_FILE="${3:-/tmp/wordstat_app.log}"

cd "$PROJECT_DIR"

if [[ ! -d .venv ]]; then
  echo "[error] .venv not found in $PROJECT_DIR"
  exit 1
fi

# Stop any process currently listening on target port.
PIDS=$(ss -lntp | awk -v p=":${PORT}" '$4 ~ p {print $NF}' | sed -E 's/.*pid=([0-9]+).*/\1/' | tr '\n' ' ')
if [[ -n "${PIDS// }" ]]; then
  kill -9 $PIDS || true
fi

# Start the intended FastAPI app from this repo explicitly.
. .venv/bin/activate
nohup python -m uvicorn --app-dir "$PROJECT_DIR" app.main:app --host 0.0.0.0 --port "$PORT" > "$LOG_FILE" 2>&1 &

sleep 1
STATUS=$(curl -s -o /tmp/wordstat_health.out -w "%{http_code}" "http://127.0.0.1:${PORT}/")
echo "HTTP status: $STATUS"
head -c 200 /tmp/wordstat_health.out || true
echo

echo "Log tail:"
tail -n 30 "$LOG_FILE" || true
