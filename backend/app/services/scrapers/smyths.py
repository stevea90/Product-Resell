"""
Smyths Toys scraper.

Strategy:
  Smyths runs on SAP Hybris. The sale page renders product tiles as traditional
  server-side HTML, so we use CSS selectors as the primary approach. We also
  check for any embedded JSON (e.g. a window.__APP_STATE__ or dataLayer push)
  as a secondary source of price data.

Sale page: https://www.smythstoys.com/uk/en-gb/sale
Product URLs are relative hrefs prefixed with https://www.smythstoys.com
"""
import json
import re
from typing import List, Optional

from parsel import Selector

from app.core.logging import get_logger
from app.services.scrapers.base import BaseScraper, ScrapedDeal
from app.services.scrapers.utils import detect_category, parse_gbp_price

logger = get_logger(__name__)

SALE_URL = "https://www.smythstoys.com/uk/en-gb/sale"
BASE_URL = "https://www.smythstoys.com"

# Smyths paginates — up to this many pages per scrape run
MAX_PAGES = 8


def _build_url(href: str) -> str:
    if not href:
        return SALE_URL
    if href.startswith("http"):
        return href
    return BASE_URL + "/" + href.lstrip("/")


def _parse_card(card: Selector) -> Optional[ScrapedDeal]:
    """Parse a single Smyths product tile."""
    try:
        title = (
            card.css(".product-title::text").get()
            or card.css(".product-name::text").get()
            or card.css("h2.name::text, h2::text, h3::text").get()
            or card.css("a[class*='title']::text").get()
            or ""
        ).strip()
        if not title:
            return None

        # Sale / current price
        price_text = (
            card.css(".sale-price::text").get()
            or card.css(".product-price .price::text").get()
            or card.css(".price::text").get()
            or card.css("[class*='sale']::text").get()
            or card.css("[class*='price']::text").get()
            or ""
        ).strip()
        deal_price = parse_gbp_price(price_text)
        if deal_price is None:
            return None

        # Was / original price
        original_text = (
            card.css(".was-price::text").get()
            or card.css(".rrp::text").get()
            or card.css("[class*='was']::text").get()
            or card.css("del::text, s::text, .old-price::text").get()
            or ""
        ).strip()
        original_price = parse_gbp_price(original_text)

        discount_percent: Optional[float] = None
        if deal_price and original_price and original_price > deal_price:
            discount_percent = round((1 - deal_price / original_price) * 100, 1)

        href = (
            card.css("a.product-title::attr(href)").get()
            or card.css("a[class*='name']::attr(href)").get()
            or card.css("a::attr(href)").get()
            or ""
        )
        source_url = _build_url(href)

        image_url = (
            card.css("img::attr(src)").get()
            or card.css("img::attr(data-src)").get()
            or card.css("img::attr(data-lazy-src)").get()
        )

        # Source ID from URL slug or data attribute
        source_id = (
            card.css("::attr(data-product-id)").get()
            or card.css("::attr(data-id)").get()
        )
        if not source_id:
            id_match = re.search(r"/p/([A-Za-z0-9]+)", href)
            source_id = id_match.group(1) if id_match else None

        return ScrapedDeal(
            source="smyths",
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
        logger.warning("smyths_card_parse_error", error=str(exc))
        return None


def _parse_page(html: str) -> List[ScrapedDeal]:
    """Parse one page of Smyths sale HTML."""
    sel = Selector(text=html)
    cards = (
        sel.css(".product-item")
        or sel.css(".product-grid .product")
        or sel.css(".product-tile")
        or sel.css("li.product")
        or sel.css(".product")
    )

    deals: List[ScrapedDeal] = []
    for card in cards:
        deal = _parse_card(card)
        if deal:
            deals.append(deal)
    return deals


def _next_page_url(html: str, current_page: int) -> Optional[str]:
    """Try to extract the next-page URL from pagination controls."""
    sel = Selector(text=html)
    next_href = (
        sel.css("a.next::attr(href)").get()
        or sel.css("[aria-label='Next']::attr(href)").get()
        or sel.css(".pagination .next a::attr(href)").get()
        or sel.css("a[class*='next']::attr(href)").get()
    )
    if next_href:
        return _build_url(next_href)
    # Try query-param pagination
    if f"?page={current_page}" in html or f"page={current_page}" in html:
        return f"{SALE_URL}?page={current_page + 1}"
    return None


class SmythsScraper(BaseScraper):
    """
    Scrapes Smyths Toys sale pages using CSS selectors.
    Handles multi-page pagination up to MAX_PAGES.
    """

    source_name = "smyths"

    async def fetch_deals(self) -> List[ScrapedDeal]:
        all_deals: List[ScrapedDeal] = []
        seen_urls: set[str] = set()
        url: Optional[str] = SALE_URL

        for page_num in range(1, MAX_PAGES + 1):
            if not url:
                break
            try:
                self.logger.info("smyths_fetch_page", page=page_num, url=url)
                response = await self._get(url)
                page_deals = _parse_page(response.text)

                added = 0
                for deal in page_deals:
                    if deal.source_url not in seen_urls:
                        seen_urls.add(deal.source_url)
                        all_deals.append(deal)
                        added += 1

                self.logger.info(
                    "smyths_page_done",
                    page=page_num,
                    deals_on_page=len(page_deals),
                    new_added=added,
                )

                # Stop if we got no new products (reached the end)
                if added == 0 and page_num > 1:
                    break

                url = _next_page_url(response.text, page_num)

            except Exception as exc:
                self.logger.error("smyths_page_error", page=page_num, url=url, error=str(exc))
                break

        self.logger.info("smyths_scrape_done", total_deals=len(all_deals))
        return all_deals
