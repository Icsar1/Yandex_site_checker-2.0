#!/usr/bin/env bash
set -euo pipefail

PORT="${PORT:-8000}"
PID_FILE="${PID_FILE:-/tmp/wordstat_app.pid}"

if [[ -f "$PID_FILE" ]]; then
  PID="$(cat "$PID_FILE")"
  if kill -0 "$PID" 2>/dev/null; then
    kill "$PID"
    rm -f "$PID_FILE"
    echo "Stopped application process $PID."
    exit 0
  fi
  rm -f "$PID_FILE"
fi

PIDS=$(ss -lntp 2>/dev/null | awk -v port=":${PORT}" '$4 ~ port"$" {print $NF}' | sed -E 's/.*pid=([0-9]+).*/\1/' | tr '\n' ' ' || true)
if [[ -n "${PIDS// }" ]]; then
  kill $PIDS || true
  echo "Stopped processes on port ${PORT}: ${PIDS}"
else
  echo "No running application process found."
fi
