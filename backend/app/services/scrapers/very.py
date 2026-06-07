"""
Very.co.uk scraper.

Strategy:
  Very is a React/SPA site. We attempt three parse strategies in order:
  1. __NEXT_DATA__ JSON embedded in a <script id="__NEXT_DATA__"> tag
  2. window.__INITIAL_STATE__ or window.APP_STATE in inline script text
  3. CSS selector fallback on rendered product tiles

Covers two category URLs:
  - Electricals & Gaming: https://www.very.co.uk/electricals-gaming/e/b/5059.end
  - Toys & Character:    https://www.very.co.uk/toys-character/e/b/5052.end
"""
import json
import re
from typing import List, Optional

from parsel import Selector

from app.core.logging import get_logger
from app.services.scrapers.base import BaseScraper, ScrapedDeal
from app.services.scrapers.utils import detect_category, parse_gbp_price

logger = get_logger(__name__)

SALE_URLS = [
    "https://www.very.co.uk/electricals-gaming/e/b/5059.end",
    "https://www.very.co.uk/toys-character/e/b/5052.end",
]
BASE_URL = "https://www.very.co.uk"

# Regex patterns for SPA state blobs
_INITIAL_STATE_RE = re.compile(
    r"window\.__INITIAL_STATE__\s*=\s*({.+?})(?:;\s*</script>|;\s*window\.)", re.DOTALL
)
_APP_STATE_RE = re.compile(
    r"window\.APP_STATE\s*=\s*({.+?})(?:;\s*</script>|;\s*window\.)", re.DOTALL
)
_REDUX_STATE_RE = re.compile(
    r"window\.__REDUX_STATE__\s*=\s*({.+?})(?:;\s*</script>)", re.DOTALL
)


def _build_url(href: str) -> str:
    if not href:
        return BASE_URL
    if href.startswith("http"):
        return href
    return BASE_URL + "/" + href.lstrip("/")


def _extract_price(obj, *keys) -> Optional[float]:
    for key in keys:
        raw = obj.get(key)
        if raw is None:
            continue
        if isinstance(raw, (int, float)):
            return round(float(raw), 2)
        if isinstance(raw, str):
            result = parse_gbp_price(raw)
            if result is not None:
                return result
        if isinstance(raw, dict):
            for sub in ("value", "amount", "price", "now"):
                v = raw.get(sub)
                if isinstance(v, (int, float)):
                    return round(float(v), 2)
                if isinstance(v, str):
                    result = parse_gbp_price(v)
                    if result is not None:
                        return result
    return None


def _product_url(product: dict) -> str:
    for key in ("url", "productUrl", "href", "canonicalUrl", "slug"):
        val = product.get(key, "")
        if val:
            return val if val.startswith("http") else _build_url(val)
    pid = product.get("id") or product.get("productId") or product.get("sku")
    return f"{BASE_URL}/product/{pid}" if pid else BASE_URL


def _parse_product(product: dict, source_url_fallback: str) -> Optional[ScrapedDeal]:
    try:
        title = (
            product.get("name")
            or product.get("title")
            or product.get("displayName")
            or product.get("productName")
            or ""
        ).strip()
        if not title:
            return None

        deal_price = _extract_price(product, "salePrice", "nowPrice", "price", "currentPrice")
        if deal_price is None:
            for nest_key in ("price", "prices", "priceInfo"):
                nested = product.get(nest_key)
                if isinstance(nested, dict):
                    deal_price = _extract_price(nested, "now", "sale", "current", "value")
                    if deal_price is not None:
                        break

        if deal_price is None:
            return None

        original_price = _extract_price(
            product, "wasPrice", "rrp", "originalPrice", "listPrice",
        )
        if original_price is None:
            for nest_key in ("price", "prices", "priceInfo"):
                nested = product.get(nest_key)
                if isinstance(nested, dict):
                    original_price = _extract_price(nested, "was", "rrp", "original")
                    if original_price is not None:
                        break

        discount_percent: Optional[float] = None
        if deal_price and original_price and original_price > deal_price:
            discount_percent = round((1 - deal_price / original_price) * 100, 1)

        source_id = str(
            product.get("id")
            or product.get("productId")
            or product.get("sku")
            or ""
        ).strip() or None

        image_url = product.get("imageUrl") or product.get("image") or product.get("thumbnail")
        if isinstance(image_url, dict):
            image_url = image_url.get("url") or image_url.get("src")

        source_url = _product_url(product) or source_url_fallback

        return ScrapedDeal(
            source="very",
            source_id=source_id,
            source_url=source_url,
            title=title,
            deal_price=deal_price,
            original_price=original_price,
            discount_percent=discount_percent,
            currency="GBP",
            image_url=image_url,
            category=detect_category(title),
        )
    except Exception as exc:
        logger.warning("very_product_parse_error", error=str(exc))
        return None


def _walk_for_products(obj, depth: int = 0) -> List[dict]:
    """Recursively find the largest list of product-like dicts."""
    if depth > 12:
        return []
    best: List[dict] = []

    if isinstance(obj, list):
        hits = [
            i for i in obj
            if isinstance(i, dict)
            and ("name" in i or "title" in i or "productName" in i)
            and ("price" in i or "salePrice" in i or "nowPrice" in i or "sku" in i)
        ]
        if len(hits) > len(best):
            best = hits
        for item in obj:
            sub = _walk_for_products(item, depth + 1)
            if len(sub) > len(best):
                best = sub

    elif isinstance(obj, dict):
        for key in ("products", "items", "results", "data", "productList"):
            if key in obj:
                sub = _walk_for_products(obj[key], depth + 1)
                if len(sub) > len(best):
                    best = sub
        for val in obj.values():
            if isinstance(val, (dict, list)):
                sub = _walk_for_products(val, depth + 1)
                if len(sub) > len(best):
                    best = sub

    return best


def _parse_html_text(html: str, source_url_fallback: str) -> List[ScrapedDeal]:
    """
    Try all three strategies against a page's HTML:
      1. __NEXT_DATA__
      2. window.__INITIAL_STATE__ / APP_STATE
      3. CSS selectors
    """
    sel = Selector(text=html)

    # --- Strategy 1: __NEXT_DATA__ ---
    raw_next = sel.css("script#__NEXT_DATA__::text").get("{}")
    try:
        data = json.loads(raw_next)
        products = _walk_for_products(data)
        if products:
            deals = [
                d for d in (_parse_product(p, source_url_fallback) for p in products)
                if d is not None
            ]
            if deals:
                logger.info("very_next_data_hit", count=len(deals))
                return deals
    except (json.JSONDecodeError, Exception) as exc:
        logger.debug("very_next_data_miss", error=str(exc))

    # --- Strategy 2: window.__INITIAL_STATE__ / APP_STATE / REDUX_STATE ---
    script_texts = sel.css("script:not([src])::text").getall()
    for pattern in (_INITIAL_STATE_RE, _APP_STATE_RE, _REDUX_STATE_RE):
        for script in script_texts:
            m = pattern.search(script)
            if m:
                try:
                    state = json.loads(m.group(1))
                    products = _walk_for_products(state)
                    if products:
                        deals = [
                            d for d in (_parse_product(p, source_url_fallback) for p in products)
                            if d is not None
                        ]
                        if deals:
                            logger.info("very_state_blob_hit", count=len(deals))
                            return deals
                except (json.JSONDecodeError, Exception) as exc:
                    logger.debug("very_state_blob_error", error=str(exc))

    # --- Strategy 3: CSS fallback ---
    deals: List[ScrapedDeal] = []
    cards = (
        sel.css(".product-list .product")
        or sel.css(".product-tile")
        or sel.css(".product-grid-item")
        or sel.css("[class*='product-item']")
    )

    for card in cards:
        try:
            title = (
                card.css(".product-title::text, .title::text, h2::text, h3::text").get()
                or ""
            ).strip()
            if not title:
                continue

            price_text = (
                card.css(".sale-price::text, .now-price::text, .price::text, [class*='price']::text").get()
                or ""
            )
            deal_price = parse_gbp_price(price_text)
            if deal_price is None:
                continue

            original_text = (
                card.css(".was-price::text, del::text, [class*='was']::text").get() or ""
            )
            original_price = parse_gbp_price(original_text)

            href = card.css("a::attr(href)").get() or ""
            source_url = _build_url(href) if href else source_url_fallback

            image_url = card.css("img::attr(src)").get()
            source_id_match = re.search(r"/(\d{5,})", href)
            source_id = source_id_match.group(1) if source_id_match else None

            discount_percent: Optional[float] = None
            if deal_price and original_price and original_price > deal_price:
                discount_percent = round((1 - deal_price / original_price) * 100, 1)

            deals.append(ScrapedDeal(
                source="very",
                source_id=source_id,
                source_url=source_url,
                title=title,
                deal_price=deal_price,
                original_price=original_price,
                discount_percent=discount_percent,
                currency="GBP",
                image_url=image_url,
                category=detect_category(title),
            ))
        except Exception as exc:
            logger.warning("very_card_parse_error", error=str(exc))

    logger.info("very_css_fallback", deals_found=len(deals))
    return deals


class VeryScraper(BaseScraper):
    """
    Scrapes Very.co.uk electricals/gaming and toys category pages.
    Attempts NEXT_DATA, window state blobs, then CSS selectors.
    """

    source_name = "very"

    async def fetch_deals(self) -> List[ScrapedDeal]:
        all_deals: List[ScrapedDeal] = []
        seen_urls: set[str] = set()

        for url in SALE_URLS:
            try:
                self.logger.info("very_fetch_start", url=url)
                response = await self._get(url)
                page_deals = _parse_html_text(response.text, url)
                for deal in page_deals:
                    if deal.source_url not in seen_urls:
                        seen_urls.add(deal.source_url)
                        all_deals.append(deal)
                self.logger.info("very_url_done", url=url, deals=len(page_deals))
            except Exception as exc:
                self.logger.error("very_fetch_error", url=url, error=str(exc))

        self.logger.info("very_scrape_done", total_deals=len(all_deals))
        return all_deals
