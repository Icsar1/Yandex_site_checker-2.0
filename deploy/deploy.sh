#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

echo "=== Yandex Mediaplan Deploy ==="

# Check .env
if [ ! -f .env ]; then
    echo "ERROR: .env file not found. Copy deploy/.env.example to .env and configure."
    exit 1
fi

# Source .env for DOMAIN check
set -a
source .env
set +a

if [ "${DOMAIN:-localhost}" = "localhost" ]; then
    echo "WARN: DOMAIN=localhost. For production, set a real domain in .env"
fi

# Pull latest code
echo "--- Pulling latest code..."
git pull --ff-only || echo "WARN: git pull failed, continuing with current code"

# Build frontend
echo "--- Building frontend..."
cd frontend
npm ci --production=false
npm run build
cd "$PROJECT_DIR"

# Copy frontend dist to a shared location for Caddy
echo "--- Preparing frontend dist..."
mkdir -p data/frontend-dist
rm -rf data/frontend-dist/*
cp -r frontend/dist/* data/frontend-dist/

# Build and start services
echo "--- Building Docker images..."
docker compose -f deploy/docker-compose.yml build

echo "--- Starting services..."
docker compose -f deploy/docker-compose.yml up -d

# Wait for healthcheck
echo "--- Waiting for API healthcheck..."
RETRIES=10
DELAY=5
for i in $(seq 1 $RETRIES); do
    if docker compose -f deploy/docker-compose.yml exec -T api curl -sf http://localhost:8000/healthz > /dev/null 2>&1; then
        echo "API is healthy!"
        break
    fi
    if [ "$i" -eq "$RETRIES" ]; then
        echo "ERROR: API did not become healthy after $((RETRIES * DELAY))s"
        docker compose -f deploy/docker-compose.yml logs api --tail=50
        exit 1
    fi
    echo "  Attempt $i/$RETRIES... waiting ${DELAY}s"
    sleep "$DELAY"
done

# Check readyz
echo "--- Checking readiness..."
if docker compose -f deploy/docker-compose.yml exec -T api curl -sf http://localhost:8000/readyz > /dev/null 2>&1; then
    echo "All systems ready!"
else
    echo "WARN: readyz returned non-200, check Redis/DB connectivity"
fi

# Cleanup old images
echo "--- Pruning old Docker images..."
docker image prune -f --filter "until=48h" 2>/dev/null || true

echo ""
echo "=== Deploy complete ==="
echo "  Domain: ${DOMAIN:-localhost}"
echo "  Health: http://localhost/healthz"
if [ "${DOMAIN:-localhost}" != "localhost" ]; then
    echo "  Web: https://${DOMAIN}"
fi
