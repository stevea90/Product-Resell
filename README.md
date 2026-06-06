# ArbitrageAI — Retail Arbitrage Intelligence Platform

An AI-powered platform that identifies high-confidence resale opportunities by combining deal feeds, Amazon marketplace data, profitability modelling, and ML-based opportunity scoring.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                     Next.js Dashboard                    │
│              (deals feed · filters · alerts)             │
└───────────────────────┬─────────────────────────────────┘
                        │ REST + WebSocket
┌───────────────────────▼─────────────────────────────────┐
│                    FastAPI Backend                       │
│   /deals   /opportunities   /analytics   /alerts        │
└──────┬──────────┬──────────┬─────────────┬──────────────┘
       │          │          │             │
┌──────▼──┐  ┌───▼────┐  ┌──▼──────┐  ┌──▼──────────┐
│ Scraper │  │Enrich  │  │Scoring  │  │Notification │
│ Workers │  │Service │  │ Engine  │  │  Service    │
│(Celery) │  │(Amazon │  │(0-100)  │  │(Email/Push) │
└──────┬──┘  │ Keepa) │  └──┬──────┘  └─────────────┘
       │     └───┬────┘     │
┌──────▼─────────▼──────────▼──────────────────────────┐
│                    PostgreSQL                          │
│  deals · products · opportunities · price_history     │
└───────────────────────────────────────────────────────┘
              │
         ┌────▼────┐
         │  Redis  │  (task queue + caching)
         └─────────┘
```

## Quick Start

### Prerequisites

- Docker + Docker Compose
- Python 3.11+
- Node.js 20+

### 1. Clone & configure

```bash
git clone <repo>
cd Product-Resell
cp .env.example .env
# Edit .env with your API keys
```

### 2. Start all services

```bash
docker compose up -d
```

### 3. Run migrations

```bash
docker compose exec backend alembic upgrade head
```

### 4. Trigger first scrape

```bash
docker compose exec backend python -m app.workers.tasks scrape_hotukdeals
```

### 5. Open dashboard

Visit http://localhost:3000

## Services

| Service      | Port | Description                        |
|-------------|------|------------------------------------|
| Dashboard    | 3000 | Next.js frontend                   |
| API          | 8000 | FastAPI backend                    |
| Flower       | 5555 | Celery task monitor                |
| PostgreSQL   | 5432 | Primary database                   |
| Redis        | 6379 | Queue + cache                      |

## Environment Variables

See `.env.example` for all required configuration.

## Development

```bash
# Backend only
cd backend && pip install -r requirements.txt
uvicorn app.main:app --reload

# Frontend only  
cd frontend && npm install && npm run dev

# Run tests
cd backend && pytest
```

## Roadmap

- [x] Phase 1: HotUKDeals scraper + Amazon enrichment + scoring + dashboard
- [ ] Phase 2: Smyths, Argos, Currys scrapers
- [ ] Phase 3: eBay marketplace analysis
- [ ] Phase 4: ML velocity prediction model
- [ ] Phase 5: TikTok trend correlation
- [ ] Phase 6: Autonomous sourcing agents
