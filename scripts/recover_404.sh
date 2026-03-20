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

if [[ ! -f app/main.py ]]; then
  echo "[error] app/main.py not found in $PROJECT_DIR"
  exit 1
fi

 codex/create-web-app-for-media-plan-using-yandex-api-f1le2c
if ! rg -n '@app.get\("/"' app/main.py >/dev/null; then
=======
if ! rg -n '@app.get("/"' app/main.py >/dev/null; then
 main
  echo "[error] route '/' is missing in $PROJECT_DIR/app/main.py"
  echo "[hint] this folder is not the expected project revision"
  exit 1
fi

# Stop any process currently listening on target port.
PIDS=$(ss -lntp | awk -v p=":${PORT}" '$4 ~ p {print $NF}' | sed -E 's/.*pid=([0-9]+).*/\1/' | tr '\n' ' ')
if [[ -n "${PIDS// }" ]]; then
  kill -9 $PIDS || true
fi

# Start the intended FastAPI app from this repo explicitly.
. .venv/bin/activate
export PYTHONPATH="$PROJECT_DIR"

echo "[info] Python imports app.main from:"
python -c 'import app.main; print(app.main.__file__)'

nohup python -m uvicorn --app-dir "$PROJECT_DIR" app.main:app --host 0.0.0.0 --port "$PORT" > "$LOG_FILE" 2>&1 &

sleep 1
STATUS=$(curl -s -o /tmp/wordstat_health.out -w "%{http_code}" "http://127.0.0.1:${PORT}/")
BODY=$(cat /tmp/wordstat_health.out 2>/dev/null || true)

echo "HTTP status: $STATUS"
head -c 200 /tmp/wordstat_health.out || true
echo

if [[ "$STATUS" == "404" && "$BODY" == *'"detail":"Not Found"'* ]]; then
  echo "[error] Uvicorn is running, but '/' is not registered in served app."
  echo "[hint] check that server path is the same repo and up-to-date:"
  echo "       cd $PROJECT_DIR && git rev-parse --abbrev-ref HEAD && git log --oneline -n 3"
fi

echo "Log tail:"
tail -n 30 "$LOG_FILE" || true
