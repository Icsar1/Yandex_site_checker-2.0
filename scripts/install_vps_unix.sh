#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="${1:-/opt/wordstat-media-planner}"
REPO_URL="${REPO_URL:-}"
BRANCH="${BRANCH:-main}"
APP_PORT="${APP_PORT:-8000}"

if [[ $EUID -ne 0 ]]; then
  echo "Run this script as root or via sudo."
  exit 1
fi

apt-get update
apt-get install -y --no-install-recommends git curl ca-certificates python3 python3-venv python3-pip fonts-dejavu-core docker.io docker-compose-plugin

if [[ ! -d "$PROJECT_DIR/.git" ]]; then
  if [[ -z "$REPO_URL" ]]; then
    echo "PROJECT_DIR does not contain a git repo. Set REPO_URL=https://... and rerun."
    exit 1
  fi
  git clone --branch "$BRANCH" "$REPO_URL" "$PROJECT_DIR"
else
  git -C "$PROJECT_DIR" fetch origin "$BRANCH"
  git -C "$PROJECT_DIR" reset --hard "origin/${BRANCH}"
fi

cd "$PROJECT_DIR"

if [[ ! -f .env ]]; then
  cat > .env <<ENVEOF
WORDSTAT_OAUTH_TOKEN=change_me
WORDSTAT_BASE_URL=https://api.wordstat.yandex.net
WORDSTAT_TIMEOUT_SECONDS=10
REQUEST_LOG_LEVEL=INFO
DEBUG=false
ENVEOF
  echo "Created .env. Edit WORDSTAT_OAUTH_TOKEN before production use."
fi

docker compose build
docker compose up -d

cat >/etc/systemd/system/wordstat-media-planner.service <<SERVICEEOF
[Unit]
Description=Wordstat Media Planner Docker Compose service
Requires=docker.service
After=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=${PROJECT_DIR}
ExecStart=/usr/bin/docker compose up -d
ExecStop=/usr/bin/docker compose down
TimeoutStartSec=0

[Install]
WantedBy=multi-user.target
SERVICEEOF

systemctl daemon-reload
systemctl enable wordstat-media-planner.service

STATUS=$(curl -s -o /tmp/wordstat_install_health.out -w "%{http_code}" "http://127.0.0.1:${APP_PORT}/" || true)
echo "Health status: ${STATUS}"
echo "Installed in ${PROJECT_DIR}. Public HTTPS should be configured separately via Nginx/reverse proxy."
