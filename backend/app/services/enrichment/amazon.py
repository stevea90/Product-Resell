"""
Amazon enrichment service.

Tries to find the best-matching Amazon UK listing for a deal, then fetches:
  - current price, buy box, historical price range
  - sales rank + estimated monthly sales
  - review count/rating
  - FBA fee estimate
  - competition (seller count)

Data hierarchy (best → fallback):
  1. Keepa API  — structured, reliable, historical price data
  2. Amazon ASIN search + page scrape — when no Keepa key

The service is designed as a reusable layer — call enrich(deal) and get back
an enriched AmazonProduct regardless of which data source was used.
"""
import re
from dataclasses import dataclass
from typing import Optional

import httpx
from parsel import Selector

from app.core.config import settings
from app.core.logging import get_logger
from app.db.models.deal import Deal

logger = get_logger(__name__)


@dataclass
class EnrichedProduct:
    """Intermediate enrichment result before DB persistence."""
    asin: Optional[str]
    amazon_url: Optional[str]
    title: Optional[str]
    brand: Optional[str]
    current_price: Optional[float]
    buy_box_price: Optional[float]
    lowest_price_30d: Optional[float]
    highest_price_30d: Optional[float]
    lowest_price_90d: Optional[float]
    buy_box_seller_count: Optional[int]
    is_amazon_selling: bool
    fba_seller_count: Optional[int]
    sales_rank: Optional[int]
    sales_rank_category: Optional[str]
    estimated_monthly_sales: Optional[int]
    review_count: Optional[int]
    review_rating: Optional[float]
    fba_fee_estimate: Optional[float]
    referral_fee_estimate: Optional[float]
    referral_fee_percent: Optional[float]
    weight_kg: Optional[float]
    data_source: str  # "keepa" | "scrape" | "mock"
    match_confidence: float  # 0–1


class KeepaClient:
    """
    Keepa API client for Amazon product data.
    Docs: https://keepa.com/#!api/0-info
    """

    BASE_URL = "https://api.keepa.com"

    def __init__(self, api_key: str) -> None:
        self.api_key = api_key
        self._client = httpx.AsyncClient(timeout=30.0)

    async def close(self) -> None:
        await self._client.aclose()

    async def search_by_title(self, title: str, domain: int = 2) -> Optional[str]:
        """
        Search Keepa for the ASIN matching a product title.
        domain=2 is Amazon UK.
        Returns the best-match ASIN or None.
        """
        url = f"{self.BASE_URL}/search"
        params = {
            "key": self.api_key,
            "domain": domain,
            "type": "product",
            "term": title[:100],
        }
        try:
            resp = await self._client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
            products = data.get("products", [])
            if products:
                return products[0].get("asin")
        except Exception as exc:
            logger.warning("keepa_search_error", error=str(exc))
        return None

    async def get_product(self, asin: str, domain: int = 2) -> Optional[dict]:
        """
        Fetch full product data for a given ASIN.
        Returns raw Keepa product dict or None.
        """
        url = f"{self.BASE_URL}/product"
        params = {
            "key": self.api_key,
            "domain": domain,
            "asin": asin,
            "history": 1,
            "stats": 90,  # Include 90-day statistics
            "offers": 20,
            "buybox": 1,
        }
        try:
            resp = await self._client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
            products = data.get("products", [])
            return products[0] if products else None
        except Exception as exc:
            logger.warning("keepa_product_error", asin=asin, error=str(exc))
        return None

    def parse_keepa_product(self, raw: dict) -> EnrichedProduct:
        """
        Convert Keepa's raw product dict into our EnrichedProduct structure.
        Keepa stores prices in cents*10 (i.e. £12.99 → 1299).
        """
        def keepa_price(val: Optional[int]) -> Optional[float]:
            if val and val > 0:
                return round(val / 100, 2)
            return None

        stats = raw.get("stats", {})
        csv = raw.get("csv", [])  # price history arrays

        # Price history is in csv[1] (Amazon price) and csv[8] (new 3P)
        current_price = keepa_price(raw.get("data", {}).get("currentPrice"))
        if not current_price and csv:
            # Last value in Amazon price history
            amazon_prices = csv[1] if len(csv) > 1 else []
            if amazon_prices:
                val = amazon_prices[-1] if isinstance(amazon_prices[-1], int) else None
                current_price = keepa_price(val)

        buy_box_price = keepa_price(raw.get("data", {}).get("buyBoxPrice"))

        # 30-day and 90-day stats
        lowest_30 = keepa_price(stats.get("avg30"))
        highest_30 = keepa_price(stats.get("max30", [None])[0] if isinstance(stats.get("max30"), list) else None)
        lowest_90 = keepa_price(stats.get("avg90"))

        # Sales rank
        sales_rank = raw.get("data", {}).get("salesRank")
        categories = raw.get("categories", [])
        rank_category = categories[0].get("name") if categories else None

        # Sales estimation from rank (rough heuristic for toys/electronics UK)
        estimated_monthly_sales = _estimate_monthly_sales_from_rank(
            sales_rank, rank_category
        )

        # Reviews
        review_count = raw.get("data", {}).get("reviewCount")
        review_rating = raw.get("data", {}).get("reviewRating")
        if review_rating:
            review_rating = review_rating / 10  # Keepa stores as 42 for 4.2

        # Seller competition
        buy_box_seller_count = raw.get("data", {}).get("buyBoxSellerCount")
        is_amazon_selling = raw.get("data", {}).get("isAmazonSelling", False)
        fba_seller_count = raw.get("data", {}).get("newOfferCount")

        # FBA fees — Keepa provides fee breakdown in fbaFees field
        fba_fees = raw.get("fbaFees", {})
        fba_fee = keepa_price(fba_fees.get("pickAndPackFee"))
        referral_pct = raw.get("data", {}).get("referralFeePercent")
        referral_pct_float = (referral_pct / 100) if referral_pct else None
        referral_fee = None
        if current_price and referral_pct_float:
            referral_fee = round(current_price * referral_pct_float, 2)

        asin = raw.get("asin", "")
        return EnrichedProduct(
            asin=asin,
            amazon_url=f"https://www.amazon.co.uk/dp/{asin}" if asin else None,
            title=raw.get("title"),
            brand=raw.get("brand"),
            current_price=current_price,
            buy_box_price=buy_box_price or current_price,
            lowest_price_30d=lowest_30,
            highest_price_30d=highest_30,
            lowest_price_90d=lowest_90,
            buy_box_seller_count=buy_box_seller_count,
            is_amazon_selling=bool(is_amazon_selling),
            fba_seller_count=fba_seller_count,
            sales_rank=sales_rank,
            sales_rank_category=rank_category,
            estimated_monthly_sales=estimated_monthly_sales,
            review_count=review_count,
            review_rating=review_rating,
            fba_fee_estimate=fba_fee or settings.fba_fulfilment_estimate_gbp,
            referral_fee_estimate=referral_fee,
            referral_fee_percent=referral_pct_float or settings.amazon_referral_fee_percent,
            weight_kg=None,
            data_source="keepa",
            match_confidence=0.9,
        )


class AmazonScrapeFallback:
    """
    Fallback scraper for when Keepa isn't configured.
    Searches Amazon UK and parses the product page.

    Note: Amazon actively blocks scrapers. This is a best-effort fallback
    for dev/testing. In production, Keepa is strongly preferred.
    """

    SEARCH_URL = "https://www.amazon.co.uk/s"

    def __init__(self) -> None:
        self._client = httpx.AsyncClient(
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                "Accept-Language": "en-GB,en;q=0.9",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            },
            follow_redirects=True,
            timeout=20.0,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def search_asin(self, title: str) -> Optional[str]:
        """Search Amazon UK for the title, return first ASIN found."""
        try:
            resp = await self._client.get(
                self.SEARCH_URL,
                params={"k": title[:100], "ref": "nb_sb_noss"},
            )
            resp.raise_for_status()
            sel = Selector(text=resp.text)

            # ASIN is in data-asin attribute of result items
            asin = sel.css("[data-asin]::attr(data-asin)").get()
            if asin and len(asin) == 10:
                return asin
        except Exception as exc:
            logger.warning("amazon_search_error", error=str(exc))
        return None

    async def fetch_product(self, asin: str) -> Optional[EnrichedProduct]:
        """Fetch and parse an Amazon product page for a given ASIN."""
        url = f"https://www.amazon.co.uk/dp/{asin}"
        try:
            resp = await self._client.get(url, params={"th": "1", "psc": "1"})
            resp.raise_for_status()
            return self._parse_product_page(resp.text, asin)
        except Exception as exc:
            logger.warning("amazon_product_fetch_error", asin=asin, error=str(exc))
        return None

    def _parse_product_page(self, html: str, asin: str) -> EnrichedProduct:
        sel = Selector(text=html)

        def text(css: str) -> str:
            return sel.css(css).get("").strip()

        def price_from(css: str) -> Optional[float]:
            t = text(css)
            return _parse_gbp_price(t)

        title = text("#productTitle::text")
        brand = text("#bylineInfo::text, .po-brand .po-break-word::text")
        current_price = price_from(".a-price .a-offscreen::text") or price_from("#priceblock_ourprice::text")
        review_count_text = text("#acrCustomerReviewText::text")
        review_count = _parse_int(review_count_text)
        rating_text = text("span[data-hook='rating-out-of-text']::text, .a-icon-star .a-icon-alt::text")
        review_rating = _parse_float(rating_text)
        sales_rank_text = text("#SalesRank .a-list-item, #detailBulletsWrapper_feature_div:contains('Best Sellers Rank')::text")
        sales_rank = _parse_int(re.sub(r"[^\d]", "", sales_rank_text.split("#")[-1][:10])) if "#" in sales_rank_text else None

        # Count sellers in "Other sellers" section
        seller_count = len(sel.css(".olp-text-col")) or None

        return EnrichedProduct(
            asin=asin,
            amazon_url=f"https://www.amazon.co.uk/dp/{asin}",
            title=title or None,
            brand=brand or None,
            current_price=current_price,
            buy_box_price=current_price,
            lowest_price_30d=None,
            highest_price_30d=None,
            lowest_price_90d=None,
            buy_box_seller_count=seller_count,
            is_amazon_selling="Ships from Amazon" in html,
            fba_seller_count=None,
            sales_rank=sales_rank,
            sales_rank_category=None,
            estimated_monthly_sales=_estimate_monthly_sales_from_rank(sales_rank, None),
            review_count=review_count,
            review_rating=review_rating,
            fba_fee_estimate=settings.fba_fulfilment_estimate_gbp,
            referral_fee_estimate=(
                round(current_price * settings.amazon_referral_fee_percent, 2)
                if current_price else None
            ),
            referral_fee_percent=settings.amazon_referral_fee_percent,
            weight_kg=None,
            data_source="scrape",
            match_confidence=0.6,
        )


class AmazonEnrichmentService:
    """
    Orchestrates enrichment: tries Keepa first, falls back to scraping.
    Returns an EnrichedProduct or None if no match found.
    """

    # Keys that mean "not configured" — skip Keepa and go straight to scraping
    _PLACEHOLDER_KEYS = {"your_keepa_api_key_here", ""}

    def __init__(self) -> None:
        self._keepa: Optional[KeepaClient] = None
        self._scrape = AmazonScrapeFallback()

        if settings.keepa_api_key not in self._PLACEHOLDER_KEYS:
            self._keepa = KeepaClient(settings.keepa_api_key)

    async def close(self) -> None:
        if self._keepa:
            await self._keepa.close()
        await self._scrape.close()

    async def enrich(self, deal: Deal) -> Optional[EnrichedProduct]:
        """
        Find the best Amazon match for this deal and return enrichment data.
        Tries Keepa first (if configured), then falls back to scraping.
        """
        search_title = self._clean_title_for_search(deal.title)
        logger.info("enriching_deal", deal_id=deal.id, title=search_title[:60])

        result: Optional[EnrichedProduct] = None

        if self._keepa:
            result = await self._enrich_via_keepa(search_title, deal)

        # Always fall back to scraping if Keepa isn't configured or finds nothing
        if result is None:
            result = await self._enrich_via_scrape(search_title, deal)

        return result

    async def _enrich_via_keepa(
        self, title: str, deal: Deal
    ) -> Optional[EnrichedProduct]:
        asin = await self._keepa.search_by_title(title)
        if not asin:
            logger.info("keepa_no_match_falling_back", deal_id=deal.id)
            return None

        raw = await self._keepa.get_product(asin)
        if not raw:
            return None

        product = self._keepa.parse_keepa_product(raw)
        logger.info("keepa_enriched", deal_id=deal.id, asin=asin, price=product.current_price)
        return product

    async def _enrich_via_scrape(
        self, title: str, deal: Deal
    ) -> Optional[EnrichedProduct]:
        asin = await self._scrape.search_asin(title)
        if not asin:
            logger.info("scrape_no_match", deal_id=deal.id)
            return None

        product = await self._scrape.fetch_product(asin)
        if product:
            logger.info("scrape_enriched", deal_id=deal.id, asin=asin)
        return product

    @staticmethod
    def _clean_title_for_search(title: str) -> str:
        """Strip deal-specific noise (% off, coupon codes, etc.) for cleaner search."""
        title = re.sub(r"\d+%\s*off", "", title, flags=re.IGNORECASE)
        title = re.sub(r"\bvoucher\b|\bcode\b|\bdeal\b|\bsale\b", "", title, flags=re.IGNORECASE)
        title = re.sub(r"\s+", " ", title).strip()
        return title[:100]


# ── Utility functions ─────────────────────────────────────────────────────────

def _estimate_monthly_sales_from_rank(
    rank: Optional[int], category: Optional[str]
) -> Optional[int]:
    """
    Rough sales velocity estimate from BSR using empirical curves.
    Source: Jungle Scout research for Amazon UK toys/electronics categories.
    These are approximations — Keepa's own estimates are more accurate.
    """
    if not rank:
        return None

    # Toys & Games category benchmarks (UK approximate)
    if rank <= 100:
        return 5000
    elif rank <= 500:
        return 2000
    elif rank <= 1000:
        return 1000
    elif rank <= 3000:
        return 500
    elif rank <= 10000:
        return 200
    elif rank <= 30000:
        return 100
    elif rank <= 100000:
        return 30
    elif rank <= 500000:
        return 10
    else:
        return 2


def _parse_gbp_price(text: str) -> Optional[float]:
    match = re.search(r"£([\d,]+\.?\d*)", text)
    if match:
        try:
            return float(match.group(1).replace(",", ""))
        except ValueError:
            pass
    return None


def _parse_int(text: str) -> Optional[int]:
    clean = re.sub(r"[^\d]", "", text)
    return int(clean) if clean else None


def _parse_float(text: str) -> Optional[float]:
    match = re.search(r"(\d+\.?\d*)", text)
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            pass
    return None
