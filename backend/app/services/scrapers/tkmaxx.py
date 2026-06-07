"""
TK Maxx scraper.

Strategy:
  TK Maxx UK does not have a public sale/clearance API. We scrape the
  'what's new' and 'sale' browse pages using CSS selectors. Their site
  occasionally embeds product JSON in script tags — we probe for that first.

  Target URLs cover the broadest possible category range since TK Maxx
  discounts are spread across home, fashion, beauty, toys, and sports.
"""
import json
import re
from typing import List, Optional

from parsel import Selector

from app.core.logging import get_logger
from app.services.scrapers.base import BaseScraper, ScrapedDeal
from app.services.scrapers.utils import detect_category, parse_gbp_price

logger = get_logger(__name__)

BASE_URL = "https://www.tkmaxx.com"
BROWSE_URLS = [
    "https://www.tkmaxx.com/uk/en/sale/c/00000000",
    "https://www.tkmaxx.com/uk/en/home/c/home",
    "https://www.tkmaxx.com/uk/en/women/c/women",
    "https://www.tkmaxx.com/uk/en/men/c/men",
    "https://www.tkmaxx.com/uk/en/kids/c/kids",
    "https://www.tkmaxx.com/uk/en/beauty/c/beauty",
    "https://www.tkmaxx.com/uk/en/sports/c/sports",
]


def _build_url(href: str) -> str:
    if not href:
        return BASE_URL
    if href.startswith("http"):
        return href
    return BASE_URL + "/" + href.lstrip("/")


def _parse_card(card: Selector, source_url_fallback: str) -> Optional[ScrapedDeal]:
    try:
        title = (
            card.css(".product-name::text").get()
            or card.css(".product-title::text").get()
            or card.css("h2::text, h3::text, [class*='title']::text").get()
            or ""
        ).strip()
        if not title:
            return None

        price_text = (
            card.css(".product-price .price::text").get()
            or card.css(".sale-price::text, .now-price::text").get()
            or card.css("[class*='sale']::text, [class*='price']::text").get()
            or ""
        ).strip()
        deal_price = parse_gbp_price(price_text)
        if deal_price is None:
            return None

        original_text = (
            card.css(".compare-at-price::text").get()
            or card.css(".was-price::text, del::text, [class*='was']::text").get()
            or ""
        ).strip()
        original_price = parse_gbp_price(original_text)

        discount_percent: Optional[float] = None
        if deal_price and original_price and original_price > deal_price:
            discount_percent = round((1 - deal_price / original_price) * 100, 1)

        href = card.css("a::attr(href)").get() or ""
        source_url = _build_url(href) if href else source_url_fallback

        image_url = (
            card.css("img::attr(src)").get()
            or card.css("img::attr(data-src)").get()
        )

        source_id = card.css("::attr(data-product-id), ::attr(data-id)").get()
        if not source_id:
            m = re.search(r"/p/([A-Za-z0-9_-]+)", href)
            source_id = m.group(1) if m else None

        return ScrapedDeal(
            source="tkmaxx",
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
        logger.warning("tkmaxx_card_parse_error", error=str(exc))
        return None


def _parse_page(html: str, source_url_fallback: str) -> List[ScrapedDeal]:
    sel = Selector(text=html)

    # Probe for embedded JSON product data
    for script in sel.css("script:not([src])::text").getall():
        if "\"products\"" in script or "\"productList\"" in script:
            # Try to extract a JSON blob
            for pattern in [
                r'window\.__INITIAL_STATE__\s*=\s*(\{.+?\});',
                r'window\.__PRELOADED_STATE__\s*=\s*(\{.+?\});',
                r'"products"\s*:\s*(\[.+?\])',
            ]:
                m = re.search(pattern, script, re.DOTALL)
                if m:
                    try:
                        data = json.loads(m.group(1))
                        products = data if isinstance(data, list) else []
                        deals = []
                        for p in products:
                            deal = _parse_json_product(p, source_url_fallback)
                            if deal:
                                deals.append(deal)
                        if deals:
                            return deals
                    except (json.JSONDecodeError, Exception):
                        pass

    cards = (
        sel.css(".product-card")
        or sel.css(".product-item")
        or sel.css(".product-tile")
        or sel.css("[class*='ProductCard']")
        or sel.css("[class*='product-card']")
    )

    deals: List[ScrapedDeal] = []
    for card in cards:
        deal = _parse_card(card, source_url_fallback)
        if deal:
            deals.append(deal)
    return deals


def _parse_json_product(product: dict, source_url_fallback: str) -> Optional[ScrapedDeal]:
    try:
        title = (product.get("name") or product.get("title") or "").strip()
        if not title:
            return None

        deal_price = None
        for key in ("salePrice", "nowPrice", "price", "currentPrice"):
            val = product.get(key)
            if val is not None:
                deal_price = parse_gbp_price(str(val)) or (float(val) if isinstance(val, (int, float)) else None)
                if deal_price:
                    break

        if deal_price is None:
            return None

        original_price = None
        for key in ("compareAtPrice", "wasPrice", "originalPrice", "rrp"):
            val = product.get(key)
            if val is not None:
                original_price = parse_gbp_price(str(val)) or (float(val) if isinstance(val, (int, float)) else None)
                if original_price:
                    break

        discount_percent: Optional[float] = None
        if deal_price and original_price and original_price > deal_price:
            discount_percent = round((1 - deal_price / original_price) * 100, 1)

        source_id = str(product.get("id") or product.get("sku") or "").strip() or None
        href = product.get("url") or product.get("href") or ""
        source_url = _build_url(href) if href else source_url_fallback
        image_url = product.get("imageUrl") or product.get("image")

        return ScrapedDeal(
            source="tkmaxx",
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
        logger.warning("tkmaxx_json_product_parse_error", error=str(exc))
        return None


class TKMaxxScraper(BaseScraper):
    """
    Scrapes TK Maxx browse/sale pages using CSS selectors.
    Covers multiple category URLs for broadest deal coverage.
    """

    source_name = "tkmaxx"

    async def fetch_deals(self) -> List[ScrapedDeal]:
        all_deals: List[ScrapedDeal] = []
        seen_urls: set[str] = set()

        for url in BROWSE_URLS:
            try:
                self.logger.info("tkmaxx_fetch_start", url=url)
                response = await self._get(url)
                page_deals = _parse_page(response.text, url)

                added = 0
                for deal in page_deals:
                    if deal.source_url not in seen_urls:
                        seen_urls.add(deal.source_url)
                        all_deals.append(deal)
                        added += 1

                self.logger.info("tkmaxx_url_done", url=url, deals=added)
            except Exception as exc:
                self.logger.error("tkmaxx_fetch_error", url=url, error=str(exc))

        self.logger.info("tkmaxx_scrape_done", total_deals=len(all_deals))
        return all_deals
