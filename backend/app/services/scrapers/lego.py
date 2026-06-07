"""
LEGO Shop scraper.

Strategy:
  1. Primary: LEGO GraphQL / product list API endpoint
     POST https://www.lego.com/api/graphql/ContentPage
     with operationName=setProductList and a JSON variables body.
  2. Fallback: HTML scraping of https://www.lego.com/en-gb/themes/sale

LEGO prices are returned as decimal pounds (e.g. 29.99).
`salePrice` is the discounted price; `regularPrice` is the original.
"""
import json
import re
from typing import List, Optional

from parsel import Selector

from app.core.logging import get_logger
from app.services.scrapers.base import BaseScraper, ScrapedDeal
from app.services.scrapers.utils import detect_category, parse_gbp_price

logger = get_logger(__name__)

SALE_PAGE_URL = "https://www.lego.com/en-gb/themes/sale"
API_URL = "https://www.lego.com/api/graphql/ContentPage"
BASE_PRODUCT_URL = "https://www.lego.com/en-gb/product"
LOCALE = "en-GB"
PAGE_SIZE = 48


def _api_variables(page: int) -> dict:
    return {
        "productListKey": "promotions-on-sale",
        "page": page,
        "locale": LOCALE,
        "pageSize": PAGE_SIZE,
    }


def _api_payload(page: int) -> dict:
    return {
        "operationName": "setProductList",
        "variables": _api_variables(page),
        "query": """
query setProductList($productListKey: String!, $page: Int, $locale: String, $pageSize: Int) {
  setProductList(
    productListKey: $productListKey
    page: $page
    locale: $locale
    pageSize: $pageSize
  ) {
    products {
      id
      setNumber
      name
      primaryImage { url }
      prices {
        regularPrice { centAmount currencyCode }
        salePrice { centAmount currencyCode }
      }
    }
    total
  }
}
""".strip(),
    }


def _cents_to_pounds(cent_amount) -> Optional[float]:
    try:
        return round(float(cent_amount) / 100, 2)
    except (TypeError, ValueError):
        return None


def _parse_api_product(product: dict) -> Optional[ScrapedDeal]:
    try:
        title = (product.get("name") or "").strip()
        if not title:
            return None

        prices = product.get("prices") or {}
        regular = prices.get("regularPrice") or {}
        sale = prices.get("salePrice") or {}

        original_price = _cents_to_pounds(regular.get("centAmount"))
        deal_price = _cents_to_pounds(sale.get("centAmount"))

        # If no sale price, fall back to regular price
        if deal_price is None:
            deal_price = original_price
            original_price = None

        if deal_price is None:
            return None

        discount_percent: Optional[float] = None
        if deal_price and original_price and original_price > deal_price:
            discount_percent = round((1 - deal_price / original_price) * 100, 1)

        product_id = str(product.get("id") or product.get("setNumber") or "").strip() or None
        image_url = None
        img = product.get("primaryImage")
        if isinstance(img, dict):
            image_url = img.get("url")
        elif isinstance(img, str):
            image_url = img

        source_url = f"{BASE_PRODUCT_URL}/{product_id}" if product_id else SALE_PAGE_URL

        return ScrapedDeal(
            source="lego_shop",
            source_id=product_id,
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
        logger.warning("lego_api_product_parse_error", error=str(exc))
        return None


def _parse_html_product(card: Selector) -> Optional[ScrapedDeal]:
    try:
        title = (
            card.css("[data-test='product-leaf-title']::text").get()
            or card.css("h2::text, h3::text, .product-title::text").get()
            or ""
        ).strip()
        if not title:
            return None

        price_text = (
            card.css("[data-test='product-price']::text").get()
            or card.css(".product-price::text, .price::text").get()
            or ""
        )
        deal_price = parse_gbp_price(price_text)
        if deal_price is None:
            return None

        original_text = (
            card.css("[data-test='product-original-price']::text").get()
            or card.css(".original-price::text, .was-price::text").get()
            or ""
        )
        original_price = parse_gbp_price(original_text)

        discount_percent: Optional[float] = None
        if deal_price and original_price and original_price > deal_price:
            discount_percent = round((1 - deal_price / original_price) * 100, 1)

        href = card.css("a::attr(href)").get() or ""
        source_url = href if href.startswith("http") else f"https://www.lego.com{href}"

        image_url = (
            card.css("img::attr(src)").get()
            or card.css("img::attr(data-src)").get()
        )

        source_id_match = re.search(r"/product/([a-z0-9-]+)", href, re.IGNORECASE)
        source_id = source_id_match.group(1) if source_id_match else None

        return ScrapedDeal(
            source="lego_shop",
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
        logger.warning("lego_html_product_parse_error", error=str(exc))
        return None


class LegoScraper(BaseScraper):
    """
    Scrapes the LEGO Shop sale/promotions pages.
    Primary: GraphQL product list API; fallback: HTML scraping.
    """

    source_name = "lego_shop"

    async def fetch_deals(self) -> List[ScrapedDeal]:
        deals = await self._fetch_via_api()
        if deals:
            self.logger.info("lego_api_success", deals_found=len(deals))
            return deals
        self.logger.info("lego_api_failed_or_empty_falling_back_to_html")
        return await self._fetch_via_html()

    async def _fetch_via_api(self) -> List[ScrapedDeal]:
        """Paginate the LEGO GraphQL product list API."""
        all_deals: List[ScrapedDeal] = []
        page = 1

        while True:
            try:
                self.logger.info("lego_api_fetch", page=page)
                response = await self._get(
                    API_URL,
                    params={
                        "operationName": "setProductList",
                        "variables": json.dumps(_api_variables(page)),
                    },
                )
                data = response.json()
                product_list = (
                    data.get("data", {}).get("setProductList", {})
                    or data.get("setProductList", {})
                )
                products = product_list.get("products", []) or []

                if not products:
                    break

                for product in products:
                    deal = _parse_api_product(product)
                    if deal:
                        all_deals.append(deal)

                total = product_list.get("total", 0)
                self.logger.info(
                    "lego_api_page_done",
                    page=page,
                    products=len(products),
                    total=total,
                )

                if len(products) < PAGE_SIZE:
                    break
                page += 1

            except Exception as exc:
                self.logger.warning("lego_api_page_error", page=page, error=str(exc))
                break

        return all_deals

    async def _fetch_via_html(self) -> List[ScrapedDeal]:
        """HTML fallback: scrape the LEGO sale page."""
        deals: List[ScrapedDeal] = []
        try:
            self.logger.info("lego_html_fetch", url=SALE_PAGE_URL)
            response = await self._get(SALE_PAGE_URL)
            sel = Selector(text=response.text)

            # Try __NEXT_DATA__ first (LEGO.com is a Next.js app)
            raw_next = sel.css("script#__NEXT_DATA__::text").get("{}")
            try:
                data = json.loads(raw_next)
                page_props = data.get("props", {}).get("pageProps", {})
                products: List[dict] = []
                for path in (["products"], ["productList", "products"], ["data", "products"]):
                    node = page_props
                    for key in path:
                        node = node.get(key, {}) if isinstance(node, dict) else {}
                    if isinstance(node, list) and node:
                        products = node
                        break

                if products:
                    for p in products:
                        deal = _parse_api_product(p)
                        if deal:
                            deals.append(deal)
                    self.logger.info("lego_html_next_data_hit", count=len(deals))
                    return deals
            except (json.JSONDecodeError, Exception) as exc:
                self.logger.debug("lego_html_next_data_miss", error=str(exc))

            # Pure CSS fallback
            cards = (
                sel.css("[data-test='product-leaf']")
                or sel.css(".product-leaf")
                or sel.css("[class*='ProductLeaf']")
                or sel.css(".product-card")
            )
            for card in cards:
                deal = _parse_html_product(card)
                if deal:
                    deals.append(deal)

            self.logger.info("lego_html_done", deals_found=len(deals))
        except Exception as exc:
            self.logger.error("lego_html_fetch_error", error=str(exc))

        return deals
