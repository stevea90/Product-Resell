"""
Home Bargains scraper.

Strategy:
  Home Bargains uses a traditional e-commerce HTML structure. We scrape
  the 'offers' and 'new products' listing pages using CSS selectors.
  The site paginates via query parameters (?p=N).

  Target: https://www.homebargains.co.uk/offers
"""
import re
from typing import List, Optional

from parsel import Selector

from app.core.logging import get_logger
from app.services.scrapers.base import BaseScraper, ScrapedDeal
from app.services.scrapers.utils import detect_category, parse_gbp_price

logger = get_logger(__name__)

BASE_URL = "https://www.homebargains.co.uk"
DEALS_URLS = [
    "https://www.homebargains.co.uk/offers",
    "https://www.homebargains.co.uk/new-products",
]
MAX_PAGES = 5


def _build_url(href: str) -> str:
    if not href:
        return BASE_URL
    if href.startswith("http"):
        return href
    return BASE_URL + "/" + href.lstrip("/")


def _parse_card(card: Selector) -> Optional[ScrapedDeal]:
    try:
        title = (
            card.css(".product-name a::text").get()
            or card.css(".product-title::text").get()
            or card.css("h2 a::text, h3 a::text").get()
            or card.css("h2::text, h3::text").get()
            or card.css("[class*='name'] a::text").get()
            or ""
        ).strip()
        if not title:
            return None

        # Home Bargains sometimes shows both a sale price and a regular price
        price_text = (
            card.css(".special-price .price::text").get()
            or card.css(".sale-price::text").get()
            or card.css(".price-box .price::text").get()
            or card.css(".price::text").get()
            or card.css("[class*='price']::text").get()
            or ""
        ).strip()
        deal_price = parse_gbp_price(price_text)
        if deal_price is None:
            return None

        original_text = (
            card.css(".old-price .price::text").get()
            or card.css(".regular-price::text").get()
            or card.css("del::text, s::text, .was::text").get()
            or ""
        ).strip()
        original_price = parse_gbp_price(original_text)

        discount_percent: Optional[float] = None
        if deal_price and original_price and original_price > deal_price:
            discount_percent = round((1 - deal_price / original_price) * 100, 1)

        href = (
            card.css("a.product-image::attr(href)").get()
            or card.css("h2 a::attr(href), h3 a::attr(href)").get()
            or card.css(".product-name a::attr(href)").get()
            or card.css("a::attr(href)").get()
            or ""
        )
        source_url = _build_url(href)

        image_url = (
            card.css("img.product-image::attr(src)").get()
            or card.css("img::attr(src)").get()
            or card.css("img::attr(data-src)").get()
        )

        source_id = card.css("::attr(data-product-id), ::attr(data-id)").get()
        if not source_id:
            m = re.search(r"/([a-z0-9-]+)/?$", href, re.IGNORECASE)
            source_id = m.group(1) if m else None

        return ScrapedDeal(
            source="homebargains",
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
        logger.warning("homebargains_card_parse_error", error=str(exc))
        return None


def _parse_page(html: str) -> List[ScrapedDeal]:
    sel = Selector(text=html)
    cards = (
        sel.css(".product-item")
        or sel.css(".product-card")
        or sel.css("li.item")
        or sel.css(".products-grid .item")
        or sel.css(".product-list .product")
    )
    deals: List[ScrapedDeal] = []
    for card in cards:
        deal = _parse_card(card)
        if deal:
            deals.append(deal)
    return deals


def _next_page_url(base_url: str, current_page: int) -> str:
    return f"{base_url}?p={current_page + 1}"


class HomeBargainsScraper(BaseScraper):
    """
    Scrapes Home Bargains offers and new-products pages using CSS selectors.
    """

    source_name = "homebargains"

    async def fetch_deals(self) -> List[ScrapedDeal]:
        all_deals: List[ScrapedDeal] = []
        seen_urls: set[str] = set()

        for start_url in DEALS_URLS:
            for page_num in range(1, MAX_PAGES + 1):
                url = start_url if page_num == 1 else _next_page_url(start_url, page_num - 1)
                try:
                    self.logger.info("homebargains_fetch_page", page=page_num, url=url)
                    response = await self._get(url)
                    page_deals = _parse_page(response.text)

                    added = 0
                    for deal in page_deals:
                        if deal.source_url not in seen_urls:
                            seen_urls.add(deal.source_url)
                            all_deals.append(deal)
                            added += 1

                    self.logger.info("homebargains_page_done", page=page_num, deals=added)

                    if added == 0 and page_num > 1:
                        break

                except Exception as exc:
                    self.logger.error("homebargains_page_error", url=url, error=str(exc))
                    break

        self.logger.info("homebargains_scrape_done", total_deals=len(all_deals))
        return all_deals
