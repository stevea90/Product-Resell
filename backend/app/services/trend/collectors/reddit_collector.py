"""
Reddit mention frequency collector.

Uses Reddit's public JSON search API (no auth required).
Counts posts mentioning the ASIN or product keyword in the last 24h.
"""
import asyncio
from datetime import date
from typing import Optional

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.logging import get_logger

logger = get_logger(__name__)

REDDIT_SEARCH_URL = "https://www.reddit.com/search.json"
SUBREDDITS = ["deals", "amazondeals", "HotDeals", "frugaluk", "unitedkingdom"]
HEADERS = {"User-Agent": "ArbitrageAI/1.0 (+https://github.com/product-resell)"}


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=2, min=3, max=30),
    reraise=False,
)
async def _search_reddit(client: httpx.AsyncClient, query: str) -> int:
    """Count Reddit posts mentioning query in the last 24h."""
    params = {"q": query, "sort": "new", "t": "day", "limit": 100, "type": "link"}
    r = await client.get(REDDIT_SEARCH_URL, params=params, headers=HEADERS)
    r.raise_for_status()
    data = r.json()
    return len(data.get("data", {}).get("children", []))


async def collect(
    asin: str,
    product_title: Optional[str],
    client: Optional[httpx.AsyncClient] = None,
    target_date: Optional[date] = None,
) -> Optional[dict]:
    """
    Return a metric dict for this ASIN's Reddit mentions today, or None on failure.
    Searches by ASIN first; falls back to first 4 words of title if ASIN gets 0 hits.
    """
    if target_date is None:
        target_date = date.today()

    own_client = client is None
    if own_client:
        client = httpx.AsyncClient(timeout=15.0)

    try:
        count = await _search_reddit(client, asin)

        # If ASIN returns nothing, try a title keyword search
        if count == 0 and product_title:
            keyword = " ".join(product_title.split()[:4])
            count = await _search_reddit(client, keyword)

        return {
            "asin": asin,
            "product_title": product_title,
            "date": target_date,
            "signal_type": "reddit_mentions",
            "value": float(count),
            "source": "reddit",
        }
    except Exception as exc:
        logger.warning("reddit_collect_failed", asin=asin, error=str(exc))
        return None
    finally:
        if own_client:
            await client.aclose()
