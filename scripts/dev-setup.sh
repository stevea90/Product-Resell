#!/usr/bin/env bash
# ============================================================
# ArbitrageAI — Quick local dev setup
# Run from the repo root: bash scripts/dev-setup.sh
# ============================================================
set -euo pipefail

echo "==> Checking prerequisites..."
command -v docker >/dev/null 2>&1 || { echo "Docker required. Install from https://docs.docker.com/get-docker/"; exit 1; }
command -v docker-compose >/dev/null 2>&1 || docker compose version >/dev/null 2>&1 || { echo "Docker Compose required."; exit 1; }

echo "==> Setting up .env..."
if [ ! -f .env ]; then
  cp .env.example .env
  echo "    Created .env — please edit it with your API keys before proceeding."
  echo "    At minimum, set KEEPA_API_KEY and ANTHROPIC_API_KEY."
fi

echo "==> Building and starting services..."
docker compose up -d --build

echo "==> Waiting for database..."
sleep 5
docker compose exec -T backend sh -c "until pg_isready -h postgres -U \$POSTGRES_USER; do sleep 1; done"

echo "==> Running database migrations..."
docker compose exec -T backend alembic upgrade head

echo "==> Triggering first scrape..."
docker compose exec -T backend python -c "
from app.workers.scraping_tasks import scrape_hotukdeals_task
scrape_hotukdeals_task.apply_async()
print('Scrape task queued!')
"

echo ""
echo "======================================================"
echo "  ArbitrageAI is running!"
echo "======================================================"
echo "  Dashboard:  http://localhost:3000"
echo "  API docs:   http://localhost:8000/docs"
echo "  Flower:     http://localhost:5555"
echo "======================================================"
echo ""
echo "To view logs:"
echo "  docker compose logs -f backend worker"
echo ""
echo "To stop everything:"
echo "  docker compose down"
