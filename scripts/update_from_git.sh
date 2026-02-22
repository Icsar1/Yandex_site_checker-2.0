#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="${1:-/root/tmp_sk/yandex_site_checker}"
BRANCH="${2:-main}"
LOG_FILE="${3:-/tmp/wordstat_deploy.log}"

cd "$PROJECT_DIR"

{
  echo "===== $(date -Iseconds) update start ====="

  git fetch origin "$BRANCH"
  BEFORE=$(git rev-parse HEAD)
  AFTER=$(git rev-parse "origin/${BRANCH}")

  if [[ "$BEFORE" == "$AFTER" ]]; then
    echo "No new commits on origin/${BRANCH}."
    exit 0
  fi

  git reset --hard "origin/${BRANCH}"

  if [[ -d .venv ]]; then
    . .venv/bin/activate
  else
    python3 -m venv --copies .venv
    . .venv/bin/activate
  fi

  pip install -r requirements.txt

  # Restart app process on port 8000.
  PIDS=$(ss -lntp | awk '$4 ~ /:8000$/ {print $NF}' | sed -E 's/.*pid=([0-9]+).*/\1/' | tr '\n' ' ')
  if [[ -n "${PIDS// }" ]]; then
    kill -9 $PIDS || true
  fi

  nohup python -m uvicorn --app-dir "$PROJECT_DIR" app.main:app --host 0.0.0.0 --port 8000 > /tmp/wordstat_app.log 2>&1 &

  sleep 1
  STATUS=$(curl -s -o /tmp/wordstat_health.out -w "%{http_code}" http://127.0.0.1:8000/)
  echo "Health status after deploy: $STATUS"
  echo "===== $(date -Iseconds) update done ====="
} >> "$LOG_FILE" 2>&1
