"""
Costco UK scraper.

Strategy:
  Costco UK runs SAP Hybris — traditional server-side HTML. We scrape
  the Clearance Products category page with CSS selectors and follow
  pagination.

Clearance URL: https://www.costco.co.uk/Clearance-Products/
"""
import json
import re
from typing import List, Optional

from parsel import Selector

from app.core.logging import get_logger
from app.services.scrapers.base import BaseScraper, ScrapedDeal
from app.services.scrapers.utils import detect_category, parse_gbp_price

logger = get_logger(__name__)

CLEARANCE_URL = "https://www.costco.co.uk/Clearance-Products/"
BASE_URL = "https://www.costco.co.uk"
MAX_PAGES = 10


def _build_url(href: str) -> str:
    if not href:
        return CLEARANCE_URL
    if href.startswith("http"):
        return href
    if href.startswith("/"):
        return BASE_URL + href
    return BASE_URL + "/" + href


def _parse_card(card: Selector) -> Optional[ScrapedDeal]:
    try:
        title = (
            card.css("h3::text").get()
            or card.css(".product-title::text").get()
            or card.css("h2::text").get()
            or card.css("a.product-name::text").get()
            or card.css("[class*='title'] a::text").get()
            or ""
        ).strip()
        if not title:
            return None

        price_text = (
            card.css(".your-price::text").get()
            or card.css(".price::text").get()
            or card.css("[class*='price']::text").get()
            or card.css("span[class*='selling']::text").get()
            or ""
        ).strip()
        deal_price = parse_gbp_price(price_text)
        if deal_price is None:
            return None

        original_text = (
            card.css(".original-price::text").get()
            or card.css(".was-price::text").get()
            or card.css("del::text, s::text").get()
            or card.css("[class*='was']::text").get()
            or ""
        ).strip()
        original_price = parse_gbp_price(original_text)

        discount_percent: Optional[float] = None
        if deal_price and original_price and original_price > deal_price:
            discount_percent = round((1 - deal_price / original_price) * 100, 1)

        href = (
            card.css("h3 a::attr(href)").get()
            or card.css(".product-title a::attr(href)").get()
            or card.css("a[class*='name']::attr(href)").get()
            or card.css("a::attr(href)").get()
            or ""
        )
        source_url = _build_url(href)

        image_url = (
            card.css("img::attr(src)").get()
            or card.css("img::attr(data-src)").get()
        )

        source_id = card.css("::attr(data-product-id)").get()
        if not source_id:
            id_match = re.search(r"/p/([A-Za-z0-9]+)", href)
            source_id = id_match.group(1) if id_match else None

        return ScrapedDeal(
            source="costco",
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
        logger.warning("costco_card_parse_error", error=str(exc))
        return None


def _parse_page(html: str) -> List[ScrapedDeal]:
    sel = Selector(text=html)
    cards = (
        sel.css(".product-list-item")
        or sel.css(".item-tile")
        or sel.css(".product")
        or sel.css("li.product")
        or sel.css("[class*='product-item']")
    )
    deals: List[ScrapedDeal] = []
    for card in cards:
        deal = _parse_card(card)
        if deal:
            deals.append(deal)
    return deals


def _next_page_url(html: str, current_page: int) -> Optional[str]:
    sel = Selector(text=html)
    next_href = (
        sel.css("a.next::attr(href)").get()
        or sel.css(".pagination a[rel='next']::attr(href)").get()
        or sel.css("[aria-label='Next']::attr(href)").get()
        or sel.css("a[class*='next']::attr(href)").get()
    )
    if next_href:
        return _build_url(next_href)
    # Hybris typically uses ?currentPage=N (0-indexed)
    if current_page == 1 or f"currentPage={current_page - 1}" in html:
        return f"{CLEARANCE_URL}?currentPage={current_page}"
    return None


class CostcoScraper(BaseScraper):
    """
    Scrapes Costco UK clearance pages using CSS selectors.
    Handles multi-page Hybris pagination.
    """

    source_name = "costco"

    async def fetch_deals(self) -> List[ScrapedDeal]:
        all_deals: List[ScrapedDeal] = []
        seen_urls: set[str] = set()
        url: Optional[str] = CLEARANCE_URL

        for page_num in range(1, MAX_PAGES + 1):
            if not url:
                break
            try:
                self.logger.info("costco_fetch_page", page=page_num, url=url)
                response = await self._get(url)
                page_deals = _parse_page(response.text)

                added = 0
                for deal in page_deals:
                    if deal.source_url not in seen_urls:
                        seen_urls.add(deal.source_url)
                        all_deals.append(deal)
                        added += 1

                self.logger.info(
                    "costco_page_done",
                    page=page_num,
                    deals_on_page=len(page_deals),
                    new_added=added,
                )

                if added == 0 and page_num > 1:
                    break

                url = _next_page_url(response.text, page_num)

            except Exception as exc:
                self.logger.error("costco_page_error", page=page_num, url=url, error=str(exc))
                break

        self.logger.info("costco_scrape_done", total_deals=len(all_deals))
        return all_deals
