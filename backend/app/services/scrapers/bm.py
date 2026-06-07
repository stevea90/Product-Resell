"""
B&M Bargains scraper.

Strategy:
  B&M's website uses a Magento-style HTML structure. We scrape the sale/offers
  landing page and follow category links. Products are in standard HTML cards.

  Target: https://www.bmstores.co.uk/offers
"""
import re
from typing import List, Optional

from parsel import Selector

from app.core.logging import get_logger
from app.services.scrapers.base import BaseScraper, ScrapedDeal
from app.services.scrapers.utils import detect_category, parse_gbp_price

logger = get_logger(__name__)

BASE_URL = "https://www.bmstores.co.uk"
DEALS_URLS = [
    "https://www.bmstores.co.uk/offers",
    "https://www.bmstores.co.uk/whats-new",
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
            or card.css(".product-title a::text").get()
            or card.css("h2 a::text, h3 a::text").get()
            or card.css("h2::text, h3::text").get()
            or card.css("[class*='title'] a::text, [class*='name'] a::text").get()
            or ""
        ).strip()
        if not title:
            return None

        price_text = (
            card.css(".special-price .price::text").get()
            or card.css(".sale-price::text").get()
            or card.css(".price::text").get()
            or card.css("[class*='price']::text").get()
            or ""
        ).strip()
        deal_price = parse_gbp_price(price_text)
        if deal_price is None:
            return None

        original_text = (
            card.css(".old-price .price::text").get()
            or card.css(".was-price::text").get()
            or card.css("del::text, s::text").get()
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
            source="bm",
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
        logger.warning("bm_card_parse_error", error=str(exc))
        return None


def _parse_page(html: str) -> List[ScrapedDeal]:
    sel = Selector(text=html)
    cards = (
        sel.css(".product-item")
        or sel.css(".product-card")
        or sel.css("li.item")
        or sel.css(".products-grid .item")
        or sel.css(".products-list .item")
    )
    deals: List[ScrapedDeal] = []
    for card in cards:
        deal = _parse_card(card)
        if deal:
            deals.append(deal)
    return deals


def _next_page_url(html: str, base_url: str, current_page: int) -> Optional[str]:
    sel = Selector(text=html)
    next_href = (
        sel.css("a.next::attr(href)").get()
        or sel.css(".pagination .next a::attr(href)").get()
        or sel.css("[rel='next']::attr(href)").get()
    )
    if next_href:
        return _build_url(next_href)
    if current_page == 1:
        return f"{base_url}?p=2"
    return None


class BMScraper(BaseScraper):
    """
    Scrapes B&M Bargains deals/new-in pages using CSS selectors.
    """

    source_name = "bm"

    async def fetch_deals(self) -> List[ScrapedDeal]:
        all_deals: List[ScrapedDeal] = []
        seen_urls: set[str] = set()

        for start_url in DEALS_URLS:
            url: Optional[str] = start_url
            for page_num in range(1, MAX_PAGES + 1):
                if not url:
                    break
                try:
                    self.logger.info("bm_fetch_page", page=page_num, url=url)
                    response = await self._get(url)
                    page_deals = _parse_page(response.text)

                    added = 0
                    for deal in page_deals:
                        if deal.source_url not in seen_urls:
                            seen_urls.add(deal.source_url)
                            all_deals.append(deal)
                            added += 1

                    self.logger.info("bm_page_done", page=page_num, deals=added)

                    if added == 0 and page_num > 1:
                        break

                    url = _next_page_url(response.text, start_url, page_num)

                except Exception as exc:
                    self.logger.error("bm_page_error", url=url, error=str(exc))
                    break

        self.logger.info("bm_scrape_done", total_deals=len(all_deals))
        return all_deals
