"""
Currys scraper.

Strategy:
  1. Primary: Parse __NEXT_DATA__ JSON — Currys uses Next.js and embeds the full
     product catalogue for each browse/clearance page in the server-rendered
     script tag.
  2. Fallback: CSS selector scraping of product card elements.

Targets the Currys clearance landing page. Price fields vary across page
versions — we probe several known keys in priority order.
"""
import json
import re
from typing import List, Optional

from parsel import Selector

from app.core.logging import get_logger
from app.services.scrapers.base import BaseScraper, ScrapedDeal
from app.services.scrapers.utils import detect_category, parse_gbp_price

logger = get_logger(__name__)

CLEARANCE_URL = "https://www.currys.co.uk/clearance"
BASE_URL = "https://www.currys.co.uk"


def _extract_price(product: dict, *keys) -> Optional[float]:
    """Try multiple dict keys for a price value; handles nested dicts."""
    for key in keys:
        raw = product.get(key)
        if raw is None:
            continue
        if isinstance(raw, (int, float)):
            # Currys prices are usually already in pounds as floats
            return round(float(raw), 2)
        if isinstance(raw, str):
            result = parse_gbp_price(raw)
            if result is not None:
                return result
        if isinstance(raw, dict):
            for sub in ("value", "amount", "price", "formattedValue"):
                if sub in raw:
                    v = raw[sub]
                    if isinstance(v, (int, float)):
                        return round(float(v), 2)
                    if isinstance(v, str):
                        result = parse_gbp_price(v)
                        if result is not None:
                            return result
    return None


def _product_url(product: dict) -> str:
    for key in ("url", "productUrl", "href", "slug", "canonicalUrl"):
        val = product.get(key, "")
        if val:
            if val.startswith("http"):
                return val
            return BASE_URL + "/" + val.lstrip("/")
    pid = product.get("id") or product.get("sku") or product.get("partNumber")
    if pid:
        return f"{BASE_URL}/product/{pid}"
    return CLEARANCE_URL


def _find_products_in_data(data: dict) -> List[dict]:
    """Walk known NEXT_DATA paths to find a product array."""
    page_props = data.get("props", {}).get("pageProps", {})

    # Priority path probes
    search_paths = [
        ["products"],
        ["initialData", "products"],
        ["initialData", "data", "products"],
        ["searchResults", "products"],
        ["categoryData", "products"],
        ["data", "products"],
        ["productList", "products"],
    ]
    for path in search_paths:
        node = page_props
        for key in path:
            node = node.get(key, {}) if isinstance(node, dict) else {}
        if isinstance(node, list) and node:
            return node

    # Broad recursive search
    return _walk_for_products(data)


def _walk_for_products(obj, depth: int = 0) -> List[dict]:
    """Recursively find the largest list of product-like objects."""
    if depth > 12:
        return []
    best: List[dict] = []

    if isinstance(obj, list):
        hits = [
            i for i in obj
            if isinstance(i, dict) and (
                "name" in i or "title" in i
            ) and (
                "price" in i or "salePrice" in i or "nowPrice" in i
                or "currentPrice" in i or "sku" in i
            )
        ]
        if len(hits) > len(best):
            best = hits
        for item in obj:
            sub = _walk_for_products(item, depth + 1)
            if len(sub) > len(best):
                best = sub

    elif isinstance(obj, dict):
        for key in ("products", "items", "results", "data"):
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


def _parse_product(product: dict) -> Optional[ScrapedDeal]:
    try:
        title = (
            product.get("name")
            or product.get("title")
            or product.get("displayName")
            or ""
        ).strip()
        if not title:
            return None

        deal_price = _extract_price(product, "salePrice", "nowPrice", "currentPrice", "price")
        # Try nested price objects
        if deal_price is None:
            for nest_key in ("prices", "price", "priceInfo"):
                nested = product.get(nest_key)
                if isinstance(nested, dict):
                    deal_price = _extract_price(
                        nested,
                        "now", "sale", "current", "displayPrice", "value",
                    )
                    if deal_price is not None:
                        break

        if deal_price is None:
            return None

        original_price = _extract_price(
            product, "wasPrice", "rrp", "originalPrice", "standardPrice", "listPrice",
        )
        if original_price is None:
            for nest_key in ("prices", "price", "priceInfo"):
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
            or product.get("partNumber")
            or ""
        ).strip() or None

        image_url = product.get("imageUrl") or product.get("image") or product.get("thumbnail")
        if isinstance(image_url, dict):
            image_url = image_url.get("url") or image_url.get("src")

        source_url = _product_url(product)
        category = detect_category(title)

        return ScrapedDeal(
            source="currys",
            source_id=source_id,
            source_url=source_url,
            title=title,
            deal_price=deal_price,
            original_price=original_price,
            discount_percent=discount_percent,
            currency="GBP",
            image_url=image_url,
            category=category,
        )
    except Exception as exc:
        logger.warning("currys_product_parse_error", error=str(exc))
        return None


class CurrysScraper(BaseScraper):
    """
    Scrapes the Currys clearance page for deals.
    Parses __NEXT_DATA__ JSON; falls back to CSS selectors.
    """

    source_name = "currys"

    async def fetch_deals(self) -> List[ScrapedDeal]:
        deals: List[ScrapedDeal] = []
        try:
            self.logger.info("currys_fetch_start", url=CLEARANCE_URL)
            response = await self._get(CLEARANCE_URL)
            sel = Selector(text=response.text)
            deals = self._parse_next_data(sel) or self._parse_html(sel)
            self.logger.info("currys_fetch_done", deals_found=len(deals))
        except Exception as exc:
            self.logger.error("currys_fetch_error", error=str(exc))
        return deals

    def _parse_next_data(self, sel: Selector) -> List[ScrapedDeal]:
        raw = sel.css("script#__NEXT_DATA__::text").get("{}")
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            self.logger.warning("currys_next_data_json_error", error=str(exc))
            return []

        products = _find_products_in_data(data)
        deals: List[ScrapedDeal] = []
        for product in products:
            deal = _parse_product(product)
            if deal:
                deals.append(deal)

        self.logger.info(
            "currys_next_data_parsed",
            products_found=len(products),
            deals_extracted=len(deals),
        )
        return deals

    def _parse_html(self, sel: Selector) -> List[ScrapedDeal]:
        """CSS fallback for Currys product cards."""
        deals: List[ScrapedDeal] = []
        cards = (
            sel.css("[data-component='product-card']")
            or sel.css(".product-card")
            or sel.css(".product-item")
            or sel.css("[class*='ProductCard']")
        )

        for card in cards:
            try:
                title = (
                    card.css("h2::text, h3::text, .product-title::text, [class*='title']::text").get()
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
                    card.css(".was-price::text, .rrp::text, [class*='was']::text").get()
                    or ""
                )
                original_price = parse_gbp_price(original_text)

                href = card.css("a::attr(href)").get() or ""
                source_url = (
                    href if href.startswith("http") else BASE_URL + "/" + href.lstrip("/")
                ) if href else CLEARANCE_URL

                image_url = card.css("img::attr(src)").get()
                source_id_match = re.search(r"[-/](\d{6,})/?$", href)
                source_id = source_id_match.group(1) if source_id_match else None

                discount_percent: Optional[float] = None
                if deal_price and original_price and original_price > deal_price:
                    discount_percent = round((1 - deal_price / original_price) * 100, 1)

                deals.append(ScrapedDeal(
                    source="currys",
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
                self.logger.warning("currys_card_parse_error", error=str(exc))

        self.logger.info("currys_html_parsed", deals_found=len(deals))
        return deals
