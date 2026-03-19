#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="${1:-/root/tmp_sk/yandex_site_checker}"
BRANCH="${2:-main}"
CRON_EXPR="${3:-* * * * *}"

CMD="cd ${PROJECT_DIR} && bash scripts/update_from_git.sh ${PROJECT_DIR} ${BRANCH}"

( crontab -l 2>/dev/null | grep -v "scripts/update_from_git.sh" || true; echo "${CRON_EXPR} ${CMD}" ) | crontab -

echo "Installed cron auto-update job:"
crontab -l | grep "scripts/update_from_git.sh" || true
