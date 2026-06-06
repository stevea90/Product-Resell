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
        Keepa stores prices in integer cents (£12.99 → 1299); -1 means N/A.

        Keepa product object field reference (domain=2, UK):
          stats.current  — array indexed by csv type: 0=Amazon, 1=New 3P, 7=BuyBox
          stats.avg30/min30/max30/avg90/min90 — same indexing, 30/90-day windows
          reviewCount    — top-level int
          rating         — top-level int (47 → 4.7 stars)
          salesRankReference — top-level int, primary category rank
          buyBoxStats    — dict keyed by seller ID → gives seller count
          fbaFees        — dict with pickAndPackFee
          categoryTree   — list of {catId, name} dicts
          packageWeight  — int, grams
        """
        def keepa_price(val) -> Optional[float]:
            if val is not None and isinstance(val, (int, float)) and val > 0:
                return round(val / 100, 2)
            return None

        stats = raw.get("stats") or {}
        csv = raw.get("csv") or []

        # Current prices from stats.current array
        current_arr = stats.get("current") or []

        def from_current(idx: int) -> Optional[float]:
            return keepa_price(current_arr[idx]) if len(current_arr) > idx else None

        amazon_price = from_current(0)   # Amazon retail price
        new_3p_price = from_current(1)   # Cheapest new 3P
        buy_box_raw = from_current(7)    # Buy Box price

        current_price = amazon_price or buy_box_raw or new_3p_price
        buy_box_price = buy_box_raw or current_price

        # 30/90-day window stats (same array indexing as current)
        def from_stats_arr(key: str, idx: int = 1) -> Optional[float]:
            arr = stats.get(key) or []
            return keepa_price(arr[idx]) if len(arr) > idx else None

        lowest_30 = from_stats_arr("min30", 1)
        highest_30 = from_stats_arr("max30", 1)
        lowest_90 = from_stats_arr("min90", 1)

        # Sales rank — top-level field in Keepa product object
        sales_rank = raw.get("salesRankReference")
        if sales_rank is not None and sales_rank < 0:
            sales_rank = None

        # Category name from categoryTree
        category_tree = raw.get("categoryTree") or []
        rank_category = category_tree[0].get("name") if category_tree else None

        # Reviews — both are top-level fields (not inside "data")
        review_count = raw.get("reviewCount")
        if review_count is not None and review_count < 0:
            review_count = None

        rating_raw = raw.get("rating")  # e.g. 47 = 4.7 stars
        review_rating = round(rating_raw / 10, 1) if rating_raw and rating_raw > 0 else None

        # Competition
        is_amazon_selling = amazon_price is not None  # Amazon has a price = they're selling
        buy_box_stats = raw.get("buyBoxStats") or {}
        buy_box_seller_count = len(buy_box_stats) if buy_box_stats else None

        # FBA fees
        fba_fees = raw.get("fbaFees") or {}
        fba_fee = keepa_price(fba_fees.get("pickAndPackFee"))

        # Weight
        weight_g = raw.get("packageWeight")
        weight_kg = round(weight_g / 1000, 3) if weight_g and weight_g > 0 else None

        # Referral fee — Keepa doesn't expose this directly; use category default
        referral_fee_percent = settings.amazon_referral_fee_percent
        referral_fee = round(current_price * referral_fee_percent, 2) if current_price else None

        asin = raw.get("asin", "")
        return EnrichedProduct(
            asin=asin,
            amazon_url=f"https://www.amazon.co.uk/dp/{asin}" if asin else None,
            title=raw.get("title"),
            brand=raw.get("brand"),
            current_price=current_price,
            buy_box_price=buy_box_price,
            lowest_price_30d=lowest_30,
            highest_price_30d=highest_30,
            lowest_price_90d=lowest_90,
            buy_box_seller_count=buy_box_seller_count,
            is_amazon_selling=is_amazon_selling,
            fba_seller_count=None,
            sales_rank=sales_rank,
            sales_rank_category=rank_category,
            estimated_monthly_sales=_estimate_monthly_sales_from_rank(sales_rank, rank_category),
            review_count=review_count,
            review_rating=review_rating,
            fba_fee_estimate=fba_fee or settings.fba_fulfilment_estimate_gbp,
            referral_fee_estimate=referral_fee,
            referral_fee_percent=referral_fee_percent,
            weight_kg=weight_kg,
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
                "Accept": (
                    "text/html,application/xhtml+xml,application/xml;"
                    "q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8"
                ),
                "Accept-Language": "en-GB,en;q=0.9",
                "Accept-Encoding": "gzip, deflate, br",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
                "Cache-Control": "max-age=0",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "none",
                "Sec-Fetch-User": "?1",
                "sec-ch-ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
                "sec-ch-ua-mobile": "?0",
                "sec-ch-ua-platform": '"Windows"',
            },
            follow_redirects=True,
            timeout=20.0,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def search_asin(self, title: str) -> Optional[str]:
        """Search Amazon UK for the title, return first non-empty ASIN."""
        try:
            resp = await self._client.get(
                self.SEARCH_URL,
                params={"k": title[:100], "ref": "nb_sb_noss"},
            )
            resp.raise_for_status()
            html = resp.text

            # Detect bot-detection / CAPTCHA pages served with 200 OK
            if "data-asin" not in html:
                if "captcha" in html.lower() or "robot" in html.lower():
                    logger.warning("amazon_captcha_detected", title=title[:40])
                else:
                    logger.warning(
                        "amazon_search_no_data_asin",
                        html_len=len(html),
                        title=title[:40],
                    )
                # Fall through to regex fallback below

            sel = Selector(text=html)

            # Try multiple CSS selectors for different Amazon page layouts
            _css_selectors = [
                "div[data-asin][data-asin!='']::attr(data-asin)",
                "[data-component-type='s-search-result']::attr(data-asin)",
                ".s-result-item[data-asin][data-asin!='']::attr(data-asin)",
                "[data-asin]::attr(data-asin)",
            ]
            for css in _css_selectors:
                asin = sel.css(css).get()
                if asin and len(asin) == 10:
                    return asin

            # Last-resort: extract ASIN from embedded JSON in the page
            for match in re.finditer(r'"asin"\s*:\s*"([A-Z0-9]{10})"', html):
                return match.group(1)

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
        # Prefer a model-number search for electronics ("LG OLED65B56LA")
        # to avoid Keepa matching a superficially similar but wrong product.
        model_term = self._model_search_term(title)
        asin = None

        if model_term:
            asin = await self._keepa.search_by_title(model_term)
            logger.info("keepa_model_search", deal_id=deal.id, term=model_term, asin=asin)

        if not asin:
            asin = await self._keepa.search_by_title(title)

        if not asin:
            logger.info("keepa_no_match_falling_back", deal_id=deal.id)
            return None

        raw = await self._keepa.get_product(asin)
        if not raw:
            return None

        product = self._keepa.parse_keepa_product(raw)

        # If we searched by model number, reject the result if the model doesn't
        # appear in the returned product title — catches Keepa returning a wrong match.
        if model_term and product.title:
            model_number = model_term.split()[-1].upper()
            if model_number not in product.title.upper():
                logger.warning(
                    "keepa_model_mismatch",
                    deal_id=deal.id,
                    searched=model_term,
                    returned=product.title[:80],
                )
                # Try broad title search as a second chance
                asin2 = await self._keepa.search_by_title(title)
                if asin2 and asin2 != asin:
                    raw2 = await self._keepa.get_product(asin2)
                    if raw2:
                        product = self._keepa.parse_keepa_product(raw2)
                        asin = asin2
                else:
                    return None  # Give up; scrape fallback will try next

        logger.info("keepa_enriched", deal_id=deal.id, asin=asin, price=product.current_price)
        return product

    async def _enrich_via_scrape(
        self, title: str, deal: Deal
    ) -> Optional[EnrichedProduct]:
        asin = await self._scrape.search_asin(title)
        if not asin:
            logger.info("scrape_no_match", deal_id=deal.id)
            # When MOCK_ENRICHMENT_FALLBACK is enabled, return synthetic data
            # so the scoring pipeline can be validated without live Amazon access
            if settings.mock_enrichment_fallback:
                logger.info("using_synthetic_enrichment", deal_id=deal.id)
                return self._create_synthetic_enrichment(deal)
            return None

        product = await self._scrape.fetch_product(asin)
        if product:
            logger.info("scrape_enriched", deal_id=deal.id, asin=asin)
        return product

    def _create_synthetic_enrichment(self, deal: Deal) -> EnrichedProduct:
        """
        Generate synthetic enrichment data when both Keepa and scraping are unavailable.
        Estimates Amazon price at a modest markup over the deal price.
        Set MOCK_ENRICHMENT_FALLBACK=true in .env to enable.
        """
        deal_price = deal.deal_price or 0
        amazon_price = round(deal_price * 1.4, 2) if deal_price else 25.0
        return EnrichedProduct(
            asin=None,
            amazon_url=None,
            title=deal.title,
            brand=None,
            current_price=amazon_price,
            buy_box_price=amazon_price,
            lowest_price_30d=round(amazon_price * 0.95, 2),
            highest_price_30d=round(amazon_price * 1.1, 2),
            lowest_price_90d=round(amazon_price * 0.92, 2),
            buy_box_seller_count=4,
            is_amazon_selling=False,
            fba_seller_count=3,
            sales_rank=45000,
            sales_rank_category="Toys & Games",
            estimated_monthly_sales=_estimate_monthly_sales_from_rank(45000, "Toys & Games"),
            review_count=87,
            review_rating=4.3,
            fba_fee_estimate=settings.fba_fulfilment_estimate_gbp,
            referral_fee_estimate=round(amazon_price * settings.amazon_referral_fee_percent, 2),
            referral_fee_percent=settings.amazon_referral_fee_percent,
            weight_kg=0.5,
            data_source="synthetic",
            match_confidence=0.25,
        )

    @staticmethod
    def _clean_title_for_search(title: str) -> str:
        """
        Strip deal-site noise from a title, leaving just the core product name.

        HotUKDeals titles often look like:
          "LG OLED65B56LA (2025) OLED 4K TV - 5 Year Warranty With Code + a £100 Gift Card My JL Members"
        We want:
          "LG OLED65B56LA OLED 4K TV"
        """
        # Cut everything from these deal-noise separators onward
        _CUTOFF_RE = re.compile(
            r"(\s+-\s+Free\b"
            r"|\s+With\s+Code\b"
            r"|\s+\+\s+(?:a\s+)?£\d"
            r"|\s+With\s+(?:BLC|HSD|EPP|Totum|Unidays)\b"
            r"|\s+My\s+JL\b"
            r"|\s*\|\s"
            r"|,\s*\d+\s*Year\s+Warranty"
            r"|\s+-\s+(?:Save|Was\s+£|Sold\s+By)"
            r"|\s+-\s+With\s+)"
            r".*$",
            re.IGNORECASE | re.DOTALL,
        )
        title = _CUTOFF_RE.sub("", title)

        # Strip remaining noise phrases
        _NOISE = [
            r"\b\d+\s*Year\s+Warranty\b",
            r"\bFree\s+(?:C&C|Click\s*&?\s*Collect|Delivery|P&P|Shipping)\b",
            r"\bWith\s+(?:Code|Voucher)\b",
            r"£[\d,]+(?:\.\d+)?\s*(?:Gift\s*Card|Cashback)\b",
            r"\d+%\s*off\b",
            r"\b(?:voucher|coupon|deal|sale)\b",
        ]
        for pattern in _NOISE:
            title = re.sub(pattern, "", title, flags=re.IGNORECASE)

        return re.sub(r"\s+", " ", title).strip().rstrip(",")[:100]

    @staticmethod
    def _model_search_term(title: str) -> Optional[str]:
        """
        If the title starts with Brand + ModelNumber, return 'Brand ModelNumber'
        for a precise Keepa search rather than the full noisy title.

        Matches patterns like:
          "LG OLED65B56LA ..."   → "LG OLED65B56LA"
          "LG 27G610A-B ..."     → "LG 27G610A-B"
          "Samsung QE65S95D ..." → "Samsung QE65S95D"
        """
        m = re.match(
            r'^([\w]+(?:\s+[\w]+)?)\s+([A-Z0-9]{2,}[-/]?[A-Z0-9]{2,})\b',
            title,
            re.IGNORECASE,
        )
        if m:
            model = m.group(2)
            # Must contain at least one digit — distinguishes model numbers from words
            if re.search(r'\d', model):
                return f"{m.group(1)} {model}"
        return None


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
