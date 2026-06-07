"""
Reddit mention frequency collector.

NOTE: Reddit's public JSON API now requires authentication (OAuth2) for
search endpoints and blocks unauthenticated requests with 403/429 errors.
This collector is disabled until Reddit OAuth credentials are configured.
"""
from datetime import date
from typing import Optional

from app.core.logging import get_logger

logger = get_logger(__name__)


async def collect(
    asin: str,
    product_title: Optional[str],
    client=None,
    target_date: Optional[date] = None,
) -> Optional[dict]:
    """Disabled — Reddit requires OAuth since mid-2023. Returns None silently."""
    return None
