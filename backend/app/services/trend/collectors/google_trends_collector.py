"""
Google Trends score collector via pytrends.

pytrends is synchronous — always run via run_in_executor to avoid
blocking the event loop. Aggressive rate limiting means we cap usage
at TOP_N ASINs per daily run and add mandatory back-off between calls.
"""
import asyncio
import time
from datetime import date
from typing import Optional

from app.core.logging import get_logger

logger = get_logger(__name__)

# Only fetch Google Trends for this many ASINs per run to avoid rate limits
TOP_N_ASINS = 15
MIN_SLEEP_SECONDS = 6  # pytrends unofficial rate limit


def _sync_fetch_trends(keyword: str) -> Optional[float]:
    """
    Synchronous pytrends call — run in executor.
    Returns a 0-100 interest score for the past 7 days, or None on failure.
    """
    try:
        from pytrends.request import TrendReq

        pt = TrendReq(hl="en-GB", tz=0, timeout=(10, 25), retries=2, backoff_factor=1.5)
        pt.build_payload([keyword], timeframe="now 7-d", geo="GB")
        df = pt.interest_over_time()

        if df.empty or keyword not in df.columns:
            return None

        # Mean of last 24h values (hourly data)
        recent = df[keyword].tail(24)
        if recent.empty:
            return None
        return float(recent.mean())
    except Exception as exc:
        logger.warning("google_trends_sync_failed", keyword=keyword, error=str(exc))
        return None


async def collect(
    asin: str,
    product_title: Optional[str],
    target_date: Optional[date] = None,
) -> Optional[dict]:
    """
    Return a metric dict for this ASIN's Google Trends score, or None on failure.
    Uses first 3 words of product title as the search keyword.
    """
    if target_date is None:
        target_date = date.today()

    if not product_title:
        return None

    # Use the most distinctive part of the title as the search term
    keyword = " ".join(product_title.split()[:3])

    loop = asyncio.get_event_loop()
    score = await loop.run_in_executor(None, _sync_fetch_trends, keyword)

    # Mandatory pause so we don't hammer Google Trends
    await asyncio.sleep(MIN_SLEEP_SECONDS)

    if score is None:
        return None

    return {
        "asin": asin,
        "product_title": product_title,
        "date": target_date,
        "signal_type": "google_trends",
        "value": score,
        "source": "google",
    }
