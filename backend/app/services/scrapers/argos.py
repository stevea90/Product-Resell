"""
Argos scraper.

Strategy:
  1. Primary: Parse __NEXT_DATA__ JSON embedded in the page — Argos is a Next.js
     app and all product data for search/browse pages is server-rendered into the
     page script tag.
  2. Fallback: CSS selector scraping of product card elements.

Targets the Argos clearance browse page. Prices in NEXT_DATA are typically
stored as integer pence (e.g. 1499 = £14.99) or as float strings with a £ prefix.
"""
import json
import re
from typing import List, Optional

from parsel import Selector

from app.core.logging import get_logger
from app.services.scrapers.base import BaseScraper, ScrapedDeal
from app.services.scrapers.utils import detect_category, parse_gbp_price

logger = get_logger(__name__)

CLEARANCE_URL = "https://www.argos.co.uk/browse/clearance/c:29867/"
BASE_URL = "https://www.argos.co.uk"


def _pence_to_pounds(value) -> Optional[float]:
    """Convert an integer pence value (e.g. 1499) to pounds (14.99)."""
    try:
        v = float(value)
        # Heuristic: if value > 1000 and looks like pence, divide by 100
        if v > 100:
            return round(v / 100, 2)
        return round(v, 2)
    except (TypeError, ValueError):
        return None


def _extract_price_field(product: dict, *keys) -> Optional[float]:
    """Try multiple key names and return the first parseable price."""
    for key in keys:
        raw = product.get(key)
        if raw is None:
            continue
        if isinstance(raw, (int, float)):
            return _pence_to_pounds(raw)
        if isinstance(raw, str):
            result = parse_gbp_price(raw)
            if result is not None:
                return result
        if isinstance(raw, dict):
            # e.g. {"value": 1499, "currency": "GBP"}
            for sub_key in ("value", "amount", "price"):
                if sub_key in raw:
                    return _pence_to_pounds(raw[sub_key])
    return None


def _build_product_url(product: dict) -> str:
    """Build a direct product URL from available fields."""
    for key in ("url", "productUrl", "href", "canonicalUrl"):
        url = product.get(key, "")
        if url:
            if url.startswith("http"):
                return url
            return BASE_URL + url.lstrip("/") if url.startswith("/") else BASE_URL + "/" + url
    # Fall back to constructing from id/partNumber
    pid = product.get("id") or product.get("partNumber") or product.get("sku")
    if pid:
        return f"{BASE_URL}/product/{pid}/"
    return CLEARANCE_URL


def _parse_product(product: dict) -> Optional[ScrapedDeal]:
    """Parse a single product dict from NEXT_DATA into a ScrapedDeal."""
    try:
        title = (
            product.get("name")
            or product.get("title")
            or product.get("displayName")
            or ""
        ).strip()
        if not title:
            return None

        deal_price = _extract_price_field(
            product,
            "retailPrice", "salePrice", "price", "nowPrice", "currentPrice",
        )
        # Also try nested price objects
        if deal_price is None:
            for nest_key in ("price", "prices", "retailPrice"):
                nested = product.get(nest_key)
                if isinstance(nested, dict):
                    deal_price = _extract_price_field(
                        nested,
                        "now", "sale", "current", "value", "amount",
                    )
                    if deal_price is not None:
                        break

        if deal_price is None:
            return None

        original_price = _extract_price_field(
            product,
            "wasPrice", "rrp", "originalPrice", "standardPrice", "listPrice",
        )
        if original_price is None:
            for nest_key in ("price", "prices", "wasPrice"):
                nested = product.get(nest_key)
                if isinstance(nested, dict):
                    original_price = _extract_price_field(
                        nested,
                        "was", "rrp", "original", "before",
                    )
                    if original_price is not None:
                        break

        discount_percent: Optional[float] = None
        if deal_price and original_price and original_price > deal_price:
            discount_percent = round((1 - deal_price / original_price) * 100, 1)

        source_id = str(
            product.get("id")
            or product.get("partNumber")
            or product.get("sku")
            or ""
        ).strip() or None

        image_url = (
            product.get("imageUrl")
            or product.get("image")
            or product.get("thumbnail")
            or None
        )
        if isinstance(image_url, dict):
            image_url = image_url.get("url") or image_url.get("src")

        source_url = _build_product_url(product)
        category = detect_category(title)

        return ScrapedDeal(
            source="argos",
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
        logger.warning("argos_product_parse_error", error=str(exc))
        return None


def _walk_next_data(obj, depth: int = 0) -> List[dict]:
    """
    Recursively walk NEXT_DATA JSON looking for arrays of product-like dicts.
    Returns the largest such array found.
    """
    if depth > 10:
        return []
    candidates: List[List[dict]] = []

    if isinstance(obj, list):
        # Check if this list contains product-like dicts
        product_like = [
            item for item in obj
            if isinstance(item, dict) and (
                "name" in item or "title" in item or "displayName" in item
            ) and (
                "retailPrice" in item or "price" in item or "salePrice" in item
                or "nowPrice" in item or "currentPrice" in item
            )
        ]
        if product_like:
            candidates.append(product_like)
        # Also recurse into list items
        for item in obj:
            candidates.extend([_walk_next_data(item, depth + 1)])

    elif isinstance(obj, dict):
        # Check priority keys first
        for key in ("results", "products", "items", "data"):
            if key in obj:
                sub = obj[key]
                if isinstance(sub, list) and sub:
                    found = _walk_next_data(sub, depth + 1)
                    if found:
                        candidates.append(found)
        for val in obj.values():
            if isinstance(val, (dict, list)):
                found = _walk_next_data(val, depth + 1)
                if found:
                    candidates.append(found)

    # Return the largest candidate list
    if candidates:
        return max(candidates, key=len)
    return []


class ArgosScraper(BaseScraper):
    """
    Scrapes the Argos clearance browse page for deals.
    Parses __NEXT_DATA__ JSON for product listings; falls back to CSS selectors.
    """

    source_name = "argos"

    async def fetch_deals(self) -> List[ScrapedDeal]:
        deals: List[ScrapedDeal] = []
        try:
            self.logger.info("argos_fetch_start", url=CLEARANCE_URL)
            response = await self._get(CLEARANCE_URL)
            sel = Selector(text=response.text)
            deals = self._parse_next_data(sel) or self._parse_html(sel)
            self.logger.info("argos_fetch_done", deals_found=len(deals))
        except Exception as exc:
            self.logger.error("argos_fetch_error", error=str(exc))
        return deals

    def _parse_next_data(self, sel: Selector) -> List[ScrapedDeal]:
        """Extract products from embedded __NEXT_DATA__ JSON."""
        raw = sel.css("script#__NEXT_DATA__::text").get("{}")
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            self.logger.warning("argos_next_data_json_error", error=str(exc))
            return []

        # Try known paths first
        page_props = data.get("props", {}).get("pageProps", {})
        products: List[dict] = []

        for path in (
            ["resultSet", "results", "products"],
            ["resultSet", "results"],
            ["searchResults", "products"],
            ["products"],
            ["items"],
            ["data", "products"],
        ):
            node = page_props
            for key in path:
                node = node.get(key, {}) if isinstance(node, dict) else {}
            if isinstance(node, list) and node:
                products = node
                break

        # If nothing found via known paths, walk the whole tree
        if not products:
            products = _walk_next_data(data)

        deals: List[ScrapedDeal] = []
        for product in products:
            deal = _parse_product(product)
            if deal:
                deals.append(deal)

        self.logger.info("argos_next_data_parsed", products_found=len(products), deals_extracted=len(deals))
        return deals

    def _parse_html(self, sel: Selector) -> List[ScrapedDeal]:
        """CSS fallback scraper for Argos product cards."""
        deals: List[ScrapedDeal] = []
        cards = (
            sel.css("[data-test='product-card']")
            or sel.css(".ProductCardstyles__Wrapper")
            or sel.css(".product-card")
        )

        for card in cards:
            try:
                title = (
                    card.css("[data-test='product-title']::text").get()
                    or card.css("h2::text, h3::text, .product-title::text").get()
                    or ""
                ).strip()
                if not title:
                    continue

                price_text = (
                    card.css("[data-test='product-price']::text").get()
                    or card.css(".price::text, .sale-price::text, [class*='price']::text").get()
                    or ""
                )
                deal_price = parse_gbp_price(price_text)
                if deal_price is None:
                    continue

                original_text = (
                    card.css("[data-test='was-price']::text").get()
                    or card.css(".was-price::text, .original-price::text, [class*='was']::text").get()
                    or ""
                )
                original_price = parse_gbp_price(original_text)

                href = (
                    card.css("a[data-test='component-product-card-title']::attr(href)").get()
                    or card.css("a::attr(href)").get()
                    or ""
                )
                source_url = (BASE_URL + href) if href.startswith("/") else href or CLEARANCE_URL

                image_url = card.css("img::attr(src)").get()
                source_id_match = re.search(r"/(\d+)/?$", href)
                source_id = source_id_match.group(1) if source_id_match else None

                discount_percent: Optional[float] = None
                if deal_price and original_price and original_price > deal_price:
                    discount_percent = round((1 - deal_price / original_price) * 100, 1)

                deals.append(ScrapedDeal(
                    source="argos",
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
                self.logger.warning("argos_card_parse_error", error=str(exc))

        self.logger.info("argos_html_parsed", deals_found=len(deals))
        return deals
