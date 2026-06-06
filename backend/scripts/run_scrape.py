"""Run a HotUKDeals scrape synchronously and print results."""
import asyncio
import sys

sys.path.insert(0, "/app")

from app.workers.scraping_tasks import _scrape_and_save


async def main():
    print("Starting HotUKDeals scrape...")
    await _scrape_and_save("hotukdeals")
    print("Scrape complete.")


asyncio.run(main())
