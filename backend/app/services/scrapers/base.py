"""
Abstract base scraper — all source scrapers inherit from this.
Provides: rate limiting, retry logic, HTTP client, user-agent rotation, logging.
"""
import asyncio
import random
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14.4; rv:125.0) Gecko/20100101 Firefox/125.0",
]

# Full browser headers — sending only User-Agent triggers 403 on most retail sites
BROWSER_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "en-GB,en;q=0.9",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "DNT": "1",
    "Cache-Control": "max-age=0",
}


@dataclass
class ScrapedDeal:
    """Normalised deal record returned by every scraper."""
    source: str
    source_id: Optional[str]
    source_url: str
    title: str
    deal_price: Optional[float]
    original_price: Optional[float]
    discount_percent: Optional[float]
    currency: str = "GBP"
    retailer: Optional[str] = None
    product_url: Optional[str] = None
    image_url: Optional[str] = None
    description: Optional[str] = None
    category: str = "other"
    hot_score: Optional[int] = None
    comment_count: Optional[int] = None
    vote_count: Optional[int] = None
    deal_posted_at: Optional[datetime] = None
    raw_data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ScrapeResult:
    """Returned by run() — wraps deals + metadata for audit logging."""
    source: str
    deals: List[ScrapedDeal]
    deals_found: int = 0
    deals_new: int = 0
    deals_duplicate: int = 0
    error: Optional[str] = None
    started_at: datetime = field(default_factory=datetime.utcnow)
    finished_at: Optional[datetime] = None

    @property
    def duration_seconds(self) -> Optional[float]:
        if self.finished_at:
            return (self.finished_at - self.started_at).total_seconds()
        return None


class BaseScraper(ABC):
    """
    All scrapers extend this. Subclasses only implement fetch_deals().
    Rate limiting, retry, and HTTP plumbing are handled here.
    """

    source_name: str = "base"

    def __init__(self) -> None:
        self._client: Optional[httpx.AsyncClient] = None
        self._semaphore = asyncio.Semaphore(settings.scraper_max_concurrency)
        self.logger = get_logger(f"scraper.{self.source_name}")

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                headers={**BROWSER_HEADERS, "User-Agent": self._random_user_agent()},
                timeout=httpx.Timeout(30.0, connect=10.0),
                follow_redirects=True,
                http2=True,
            )
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    def _random_user_agent(self) -> str:
        return random.choice(USER_AGENTS)

    def _rotate_user_agent(self) -> None:
        if self._client:
            self._client.headers.update({"User-Agent": self._random_user_agent()})

    async def _rate_limit(self) -> None:
        """Polite delay between requests to avoid bans."""
        delay = settings.scraper_request_delay_seconds
        jitter = random.uniform(0.5, 1.5)
        await asyncio.sleep(delay * jitter)

    @retry(
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.NetworkError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    async def _get(self, url: str, **kwargs) -> httpx.Response:
        """GET with automatic retry on transient network errors."""
        async with self._semaphore:
            self._rotate_user_agent()
            self.logger.debug("fetching", url=url)
            response = await self.client.get(url, **kwargs)
            response.raise_for_status()
            await self._rate_limit()
            return response

    @abstractmethod
    async def fetch_deals(self) -> List[ScrapedDeal]:
        """
        Subclasses implement this. Returns a list of ScrapedDeal objects.
        Should handle pagination internally.
        """
        ...

    async def run(self) -> ScrapeResult:
        """Entry point. Fetches deals and wraps in a ScrapeResult."""
        result = ScrapeResult(source=self.source_name, deals=[])
        try:
            self.logger.info("scrape_started", source=self.source_name)
            result.deals = await self.fetch_deals()
            result.deals_found = len(result.deals)
            self.logger.info(
                "scrape_complete",
                source=self.source_name,
                deals_found=result.deals_found,
            )
        except Exception as exc:
            result.error = str(exc)
            self.logger.error("scrape_failed", source=self.source_name, error=str(exc), exc_info=True)
        finally:
            result.finished_at = datetime.utcnow()
            await self.close()
        return result
