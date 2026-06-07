"""
Boots scraper.

Strategy:
  1. Primary: Parse __NEXT_DATA__ JSON — Boots.com is a Next.js app and embeds
     product data in the page script tag.
  2. Fallback: CSS selector scraping of product grid items.

Targets the Boots offers page which covers health, beauty, and electricals.
"""
import json
import re
from typing import List, Optional

from parsel import Selector

from app.core.logging import get_logger
from app.services.scrapers.base import BaseScraper, ScrapedDeal
from app.services.scrapers.utils import detect_category, parse_gbp_price

logger = get_logger(__name__)

OFFERS_URL = "https://www.boots.com/offers"
BASE_URL = "https://www.boots.com"
MAX_PAGES = 8


def _build_url(href: str) -> str:
    if not href:
        return OFFERS_URL
    if href.startswith("http"):
        return href
    if href.startswith("/"):
        return BASE_URL + href
    return BASE_URL + "/" + href


def _extract_price(obj: dict, *keys) -> Optional[float]:
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
            for sub in ("value", "amount", "price", "formattedValue"):
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
    pid = product.get("id") or product.get("sku") or product.get("productId")
    return f"{BASE_URL}/product/{pid}" if pid else OFFERS_URL


def _walk_for_products(obj, depth: int = 0) -> List[dict]:
    if depth > 12:
        return []
    best: List[dict] = []

    if isinstance(obj, list):
        hits = [
            i for i in obj
            if isinstance(i, dict)
            and ("name" in i or "title" in i or "displayName" in i)
            and ("price" in i or "salePrice" in i or "nowPrice" in i
                 or "currentPrice" in i or "sku" in i)
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


def _parse_api_product(product: dict) -> Optional[ScrapedDeal]:
    try:
        title = (
            product.get("name")
            or product.get("title")
            or product.get("displayName")
            or ""
        ).strip()
        if not title:
            return None

        deal_price = _extract_price(
            product, "salePrice", "nowPrice", "currentPrice", "price",
        )
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
            or product.get("sku")
            or product.get("productId")
            or ""
        ).strip() or None

        image_url = product.get("imageUrl") or product.get("image") or product.get("thumbnail")
        if isinstance(image_url, dict):
            image_url = image_url.get("url") or image_url.get("src")

        source_url = _product_url(product)

        return ScrapedDeal(
            source="boots",
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
        logger.warning("boots_product_parse_error", error=str(exc))
        return None


def _parse_html_card(card: Selector) -> Optional[ScrapedDeal]:
    try:
        title = (
            card.css("h2::text, h3::text").get()
            or card.css(".product-title::text, .product-name::text").get()
            or card.css("a[class*='title']::text").get()
            or ""
        ).strip()
        if not title:
            return None

        price_text = (
            card.css(".price::text, .sale-price::text").get()
            or card.css("[class*='price']::text").get()
            or ""
        )
        deal_price = parse_gbp_price(price_text)
        if deal_price is None:
            return None

        original_text = (
            card.css(".was-price::text, del::text, [class*='was']::text").get() or ""
        )
        original_price = parse_gbp_price(original_text)

        discount_percent: Optional[float] = None
        if deal_price and original_price and original_price > deal_price:
            discount_percent = round((1 - deal_price / original_price) * 100, 1)

        href = card.css("a::attr(href)").get() or ""
        source_url = _build_url(href) if href else OFFERS_URL

        image_url = card.css("img::attr(src)").get()
        source_id_match = re.search(r"/([A-Z0-9]{6,})", href, re.IGNORECASE)
        source_id = source_id_match.group(1) if source_id_match else None

        return ScrapedDeal(
            source="boots",
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
        logger.warning("boots_card_parse_error", error=str(exc))
        return None


class BootsScraper(BaseScraper):
    """
    Scrapes Boots.com offers page for health, beauty, and electricals deals.
    Primary: __NEXT_DATA__ JSON parsing; fallback: CSS selectors.
    """

    source_name = "boots"

    async def fetch_deals(self) -> List[ScrapedDeal]:
        all_deals: List[ScrapedDeal] = []
        seen_urls: set[str] = set()

        try:
            self.logger.info("boots_fetch_start", url=OFFERS_URL)
            response = await self._get(OFFERS_URL)
            sel = Selector(text=response.text)

            # Strategy 1: __NEXT_DATA__
            raw_next = sel.css("script#__NEXT_DATA__::text").get("{}")
            try:
                data = json.loads(raw_next)
                products = _walk_for_products(data)
                if products:
                    for product in products:
                        deal = _parse_api_product(product)
                        if deal and deal.source_url not in seen_urls:
                            seen_urls.add(deal.source_url)
                            all_deals.append(deal)
                    self.logger.info(
                        "boots_next_data_hit",
                        products_found=len(products),
                        deals=len(all_deals),
                    )
                    return all_deals
            except (json.JSONDecodeError, Exception) as exc:
                self.logger.debug("boots_next_data_miss", error=str(exc))

            # Strategy 2: CSS selectors
            cards = (
                sel.css(".product-list .product")
                or sel.css(".product-grid__item")
                or sel.css(".product-item")
                or sel.css("[class*='product-tile']")
            )
            for card in cards:
                deal = _parse_html_card(card)
                if deal and deal.source_url not in seen_urls:
                    seen_urls.add(deal.source_url)
                    all_deals.append(deal)

            self.logger.info("boots_css_fallback_done", deals=len(all_deals))

        except Exception as exc:
            self.logger.error("boots_fetch_error", error=str(exc))

        self.logger.info("boots_scrape_done", total_deals=len(all_deals))
        return all_deals
