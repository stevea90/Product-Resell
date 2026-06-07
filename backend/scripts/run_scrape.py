"""Run all registered scrapers sequentially and print results."""
import asyncio
import sys

sys.path.insert(0, "/app")

from app.services.scrapers import SCRAPER_REGISTRY
from app.workers.scraping_tasks import _scrape_and_save


async def main():
    sources = list(SCRAPER_REGISTRY.keys())
    print(f"Scraping {len(sources)} sources: {', '.join(sources)}\n")

    for source in sources:
        print(f"[{source}] Starting...")
        try:
            await _scrape_and_save(source)
            print(f"[{source}] Done.")
        except Exception as exc:
            print(f"[{source}] ERROR: {exc}")

    print("\nAll scrapes complete.")


asyncio.run(main())
