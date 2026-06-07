"""
Ebuyer scraper.

Strategy:
  Ebuyer is a traditional HTML e-commerce site. We scrape the deals/offers
  listing page using CSS selectors with multi-page pagination.

Deals URL: https://www.ebuyer.com/deals
"""
import json
import re
from typing import List, Optional

from parsel import Selector

from app.core.logging import get_logger
from app.services.scrapers.base import BaseScraper, ScrapedDeal
from app.services.scrapers.utils import detect_category, parse_gbp_price

logger = get_logger(__name__)

DEALS_URL = "https://www.ebuyer.com/clearance"
BASE_URL = "https://www.ebuyer.com"
MAX_PAGES = 10


def _build_url(href: str) -> str:
    if not href:
        return DEALS_URL
    if href.startswith("http"):
        return href
    if href.startswith("/"):
        return BASE_URL + href
    return BASE_URL + "/" + href


def _parse_card(card: Selector) -> Optional[ScrapedDeal]:
    try:
        title = (
            card.css(".product-title::text").get()
            or card.css(".title::text").get()
            or card.css("h2 a::text").get()
            or card.css("h2::text, h3::text").get()
            or card.css("a.title::text").get()
            or ""
        ).strip()
        if not title:
            return None

        price_text = (
            card.css(".now-price::text").get()
            or card.css(".deal-price::text").get()
            or card.css(".price::text").get()
            or card.css("[class*='price']::text").get()
            or card.css("span.selling-price::text").get()
            or ""
        ).strip()
        deal_price = parse_gbp_price(price_text)
        if deal_price is None:
            return None

        original_text = (
            card.css(".was-price::text").get()
            or card.css(".old-price::text").get()
            or card.css("del::text, s::text").get()
            or card.css("[class*='was']::text").get()
            or ""
        ).strip()
        original_price = parse_gbp_price(original_text)

        discount_percent: Optional[float] = None
        if deal_price and original_price and original_price > deal_price:
            discount_percent = round((1 - deal_price / original_price) * 100, 1)

        href = (
            card.css("h2 a::attr(href)").get()
            or card.css(".product-title a::attr(href)").get()
            or card.css("a[class*='title']::attr(href)").get()
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
            id_match = re.search(r"/(\d+)-", href)
            source_id = id_match.group(1) if id_match else None

        return ScrapedDeal(
            source="ebuyer",
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
        logger.warning("ebuyer_card_parse_error", error=str(exc))
        return None


def _parse_page(html: str) -> List[ScrapedDeal]:
    sel = Selector(text=html)
    cards = (
        sel.css(".product-listing")
        or sel.css(".item")
        or sel.css(".product")
        or sel.css("li[class*='product']")
        or sel.css("article[class*='product']")
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
        sel.css("a[rel='next']::attr(href)").get()
        or sel.css(".pagination a.next::attr(href)").get()
        or sel.css("[aria-label='Next']::attr(href)").get()
        or sel.css("a[class*='next']::attr(href)").get()
    )
    if next_href:
        return _build_url(next_href)
    # Ebuyer commonly uses ?page=N
    if current_page == 1 or f"page={current_page}" in html:
        return f"{DEALS_URL}?page={current_page + 1}"
    return None


class EbuyerScraper(BaseScraper):
    """
    Scrapes Ebuyer deals listing pages using CSS selectors.
    Handles multi-page pagination.
    """

    source_name = "ebuyer"

    async def fetch_deals(self) -> List[ScrapedDeal]:
        all_deals: List[ScrapedDeal] = []
        seen_urls: set[str] = set()
        url: Optional[str] = DEALS_URL

        for page_num in range(1, MAX_PAGES + 1):
            if not url:
                break
            try:
                self.logger.info("ebuyer_fetch_page", page=page_num, url=url)
                response = await self._get(url)
                page_deals = _parse_page(response.text)

                added = 0
                for deal in page_deals:
                    if deal.source_url not in seen_urls:
                        seen_urls.add(deal.source_url)
                        all_deals.append(deal)
                        added += 1

                self.logger.info(
                    "ebuyer_page_done",
                    page=page_num,
                    deals_on_page=len(page_deals),
                    new_added=added,
                )

                if added == 0 and page_num > 1:
                    break

                url = _next_page_url(response.text, page_num)

            except Exception as exc:
                self.logger.error("ebuyer_page_error", page=page_num, url=url, error=str(exc))
                break

        self.logger.info("ebuyer_scrape_done", total_deals=len(all_deals))
        return all_deals
