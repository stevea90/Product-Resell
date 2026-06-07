"""
Run the full trend ingestion pipeline right now (without waiting for 2am).

Steps:
  1. Ingest metrics  — Amazon, HotUKDeals, Reddit, Google Trends
  2. Compute trends  — demand score, MAs, z-score for every ASIN
  3. Detect anomalies — z-score spike alerts

Usage (from project root):
  docker compose exec backend python scripts/run_trend_ingest.py
"""
import asyncio
import sys
import time

sys.path.insert(0, "/app")

from app.db.database import engine, get_db_context
from app.services.trend.trend_service import TrendService


async def main():
    print("=" * 60)
    print("Demand Trend Ingestion — manual run")
    print("=" * 60)

    # ── Step 1: Ingest metrics ─────────────────────────────────
    print("\n[1/3] Ingesting metrics (Amazon, HotUKDeals, Reddit, Google Trends)...")
    print("      This may take 2-3 minutes due to Google Trends rate limits.\n")
    t0 = time.time()
    async with get_db_context() as db:
        svc = TrendService(db)
        asins = await svc.get_all_tracked_asins()

    print(f"      Found {len(asins)} tracked ASINs.")

    if not asins:
        print("\n  No ASINs found — run a scrape first to populate products.")
        print("  docker compose exec backend python scripts/run_scrape.py")
        await engine.dispose()
        return

    async with get_db_context() as db:
        svc = TrendService(db)
        total_metrics = await svc.ingest_all_metrics()

    print(f"      Metrics saved: {total_metrics}  ({time.time() - t0:.0f}s)")

    # ── Step 2: Compute trends ─────────────────────────────────
    print("\n[2/3] Computing demand scores and moving averages...")
    t1 = time.time()
    async with get_db_context() as db:
        svc = TrendService(db)
        asins = await svc.get_all_tracked_asins()

    computed = 0
    errors = 0
    for asin, title in asins:
        try:
            async with get_db_context() as db:
                svc = TrendService(db)
                trend = await svc.compute_trend_for_asin(asin, title)
            if trend:
                computed += 1
                label = (title or asin)[:55]
                print(f"      {label:<55}  score={trend.demand_score:>5.1f}  dir={trend.trend_direction}")
        except Exception as exc:
            errors += 1
            print(f"      ERROR [{asin}]: {exc}")

    print(f"\n      Computed: {computed}  Errors: {errors}  ({time.time() - t1:.0f}s)")

    # ── Step 3: Detect anomalies ───────────────────────────────
    print("\n[3/3] Detecting anomalies...")
    t2 = time.time()
    async with get_db_context() as db:
        svc = TrendService(db)
        asins = await svc.get_all_tracked_asins()

    total_anomalies = 0
    for asin, title in asins:
        try:
            async with get_db_context() as db:
                svc = TrendService(db)
                found = await svc.detect_anomalies_for_asin(asin, title)
            for a in found:
                total_anomalies += 1
                print(f"      [{a.severity.upper():8}] {a.signal_type:<20} z={a.z_score:+.2f}  {(title or asin)[:40]}")
        except Exception as exc:
            print(f"      ERROR [{asin}]: {exc}")

    if total_anomalies == 0:
        print("      No anomalies detected (need 7+ days of history for reliable z-scores).")

    print(f"\n      Anomalies saved: {total_anomalies}  ({time.time() - t2:.0f}s)")

    # ── Summary ────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("Done! Refresh the dashboard to see Market Intelligence data.")
    print("=" * 60)

    await engine.dispose()


asyncio.run(main())
