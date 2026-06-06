"""
HotUKDeals scraper.

Strategy:
  1. Primary: RSS feed (https://www.hotukdeals.com/rss/deals) — fast, stable, no JS needed
  2. Fallback: HTML scraping of hot deals listing

HotUKDeals is a community deal site. Their temperature/hot score and comment
count are strong demand-signal proxies — high temperature = proven community
interest, which correlates with sellable products.

Category detection is applied via keyword matching on the title to route deals
into our target niches (toys, LEGO, gaming, electronics).
"""
import re
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import List, Optional
from email.utils import parsedate_to_datetime

from parsel import Selector

from app.core.logging import get_logger
from app.services.scrapers.base import BaseScraper, ScrapedDeal

logger = get_logger(__name__)

# Category detection keyword map — order matters (most specific first)
CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "lego": [
        "lego", "lego technic", "lego star wars", "lego city",
        "lego creator", "lego friends", "lego harry potter",
    ],
    "gaming": [
        "playstation", "ps5", "ps4", "xbox", "nintendo switch",
        "game", "gaming", "steam deck", "controller", "console",
        "pokemon", "zelda", "mario",
    ],
    "toys": [
        "toy", "nerf", "barbie", "hot wheels", "action figure",
        "playset", "smyths", "funko", "plush", "doll",
    ],
    "electronics": [
        "laptop", "tablet", "ipad", "iphone", "samsung", "tv",
        "monitor", "headphone", "earbuds", "airpods", "speaker",
        "camera", "drone", "apple", "sony", "lg",
    ],
}

# Target minimum hot score — below this, deal is unlikely to be worth analysing
MIN_HOT_SCORE = 100

# Maximum pages to scrape per run (each page = 30 deals)
MAX_PAGES = 5

RSS_FEEDS = {
    "hot": "https://www.hotukdeals.com/rss/deals?filter=all",
    "toys": "https://www.hotukdeals.com/rss/deals?catid=toys",
    "gaming": "https://www.hotukdeals.com/rss/deals?catid=gaming",
    "tech": "https://www.hotukdeals.com/rss/deals?catid=technology",
}


def _detect_category(title: str) -> str:
    lower = title.lower()
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(kw in lower for kw in keywords):
            return category
    return "other"


def _extract_price(text: Optional[str]) -> Optional[float]:
    """Extract first GBP price from a string like '£12.99' or 'Was £24.99'."""
    if not text:
        return None
    match = re.search(r"£([\d,]+\.?\d*)", text)
    if match:
        try:
            return float(match.group(1).replace(",", ""))
        except ValueError:
            pass
    return None


def _parse_rss_item(item: ET.Element, ns: dict) -> Optional[ScrapedDeal]:
    """Parse a single RSS <item> element into a ScrapedDeal."""
    try:
        title = item.findtext("title", "").strip()
        link = item.findtext("link", "").strip()
        description_html = item.findtext("description", "")
        pub_date_str = item.findtext("pubDate", "")
        guid = item.findtext("guid", link)

        if not title or not link:
            return None

        # Parse publication date
        deal_posted_at: Optional[datetime] = None
        if pub_date_str:
            try:
                deal_posted_at = parsedate_to_datetime(pub_date_str)
            except Exception:
                pass

        # Parse description HTML for price, image, hot score
        sel = Selector(text=description_html)

        # Extract image
        image_url = sel.css("img::attr(src)").get()

        # Try to find prices and temperature from the description text
        desc_text = sel.css("*").getall()
        full_text = " ".join(desc_text)

        deal_price = _extract_price(sel.css(".deal-price::text, .price::text").get() or full_text)
        original_price = _extract_price(sel.css(".old-price::text, .was-price::text").get())

        # Hot score often appears in description as "Temperature: 245°"
        hot_score: Optional[int] = None
        temp_match = re.search(r"(\d+)\s*°", full_text)
        if temp_match:
            hot_score = int(temp_match.group(1))

        # Comment count
        comment_count: Optional[int] = None
        comment_match = re.search(r"(\d+)\s+comment", full_text, re.IGNORECASE)
        if comment_match:
            comment_count = int(comment_match.group(1))

        # Discount percent
        discount_percent: Optional[float] = None
        if deal_price and original_price and original_price > deal_price:
            discount_percent = round((1 - deal_price / original_price) * 100, 1)

        category = _detect_category(title)
        source_id = re.search(r"/(\d+)", guid or link)

        return ScrapedDeal(
            source="hotukdeals",
            source_id=source_id.group(1) if source_id else None,
            source_url=link,
            title=title,
            deal_price=deal_price,
            original_price=original_price,
            discount_percent=discount_percent,
            currency="GBP",
            product_url=link,
            image_url=image_url,
            description=sel.css("p::text").get("").strip() or None,
            category=category,
            hot_score=hot_score,
            comment_count=comment_count,
            deal_posted_at=deal_posted_at,
        )
    except Exception as exc:
        logger.warning("rss_item_parse_error", error=str(exc))
        return None


class HotUKDealsScraper(BaseScraper):
    """
    Fetches deals from HotUKDeals using their public RSS feeds.
    Targets the hot/toys/gaming/tech category feeds simultaneously.
    Only surfaces deals in our target categories.
    """

    source_name = "hotukdeals"

    async def fetch_deals(self) -> List[ScrapedDeal]:
        all_deals: List[ScrapedDeal] = []
        seen_urls: set[str] = set()

        for feed_name, feed_url in RSS_FEEDS.items():
            try:
                self.logger.info("fetching_rss_feed", feed=feed_name)
                response = await self._get(feed_url)
                deals = self._parse_rss_feed(response.text, feed_name)

                for deal in deals:
                    if deal.source_url not in seen_urls:
                        # Only keep target categories
                        if deal.category != "other":
                            seen_urls.add(deal.source_url)
                            all_deals.append(deal)

                self.logger.info(
                    "rss_feed_parsed",
                    feed=feed_name,
                    deals_found=len(deals),
                    deals_kept=sum(1 for d in deals if d.category != "other"),
                )
            except Exception as exc:
                self.logger.error("rss_feed_error", feed=feed_name, error=str(exc))

        self.logger.info(
            "hotukdeals_scrape_done",
            total_deals=len(all_deals),
            categories={c: sum(1 for d in all_deals if d.category == c) for c in CATEGORY_KEYWORDS},
        )
        return all_deals

    def _parse_rss_feed(self, xml_text: str, feed_name: str) -> List[ScrapedDeal]:
        """Parse RSS XML and return list of ScrapedDeal objects."""
        deals: List[ScrapedDeal] = []
        try:
            # Strip BOM if present
            xml_text = xml_text.lstrip("﻿")
            root = ET.fromstring(xml_text)
            ns: dict = {}

            channel = root.find("channel")
            if channel is None:
                return deals

            for item in channel.findall("item"):
                deal = _parse_rss_item(item, ns)
                if deal:
                    deals.append(deal)

        except ET.ParseError as exc:
            self.logger.error("rss_parse_error", feed=feed_name, error=str(exc))

        return deals

    async def fetch_html_page(self, page: int = 1) -> List[ScrapedDeal]:
        """
        Fallback HTML scraper for when RSS doesn't have enough data.
        Scrapes the HotUKDeals deals listing page directly.
        """
        url = f"https://www.hotukdeals.com/deals?page={page}"
        response = await self._get(url)
        sel = Selector(text=response.text)
        deals: List[ScrapedDeal] = []

        for article in sel.css("article.thread--deal, li.thread--type-deal"):
            try:
                title = (
                    article.css(".thread-title a::text, .cept-tt::text").get("").strip()
                )
                link = article.css(".thread-title a::attr(href), .cept-tt::attr(href)").get("")
                if not title or not link:
                    continue

                if not link.startswith("http"):
                    link = f"https://www.hotukdeals.com{link}"

                price_text = article.css(".thread-price::text, .deal-price::text").get("")
                original_text = article.css(".text--lineThrough::text").get("")
                image = article.css("img.thread-image::attr(src), img::attr(src)").get()
                temp_text = article.css(".vote-temp::text, .cept-vote-temp::text").get("0")
                comments_text = article.css(".vote-box--comments::text, .cept-comments-count::text").get("0")

                deal_price = _extract_price(price_text)
                original_price = _extract_price(original_text)
                hot_score = int(re.sub(r"[^\d]", "", temp_text) or 0)
                comment_count = int(re.sub(r"[^\d]", "", comments_text) or 0)

                discount_percent: Optional[float] = None
                if deal_price and original_price and original_price > deal_price:
                    discount_percent = round((1 - deal_price / original_price) * 100, 1)

                source_id_match = re.search(r"/(\d+)", link)

                deals.append(ScrapedDeal(
                    source="hotukdeals",
                    source_id=source_id_match.group(1) if source_id_match else None,
                    source_url=link,
                    title=title,
                    deal_price=deal_price,
                    original_price=original_price,
                    discount_percent=discount_percent,
                    currency="GBP",
                    image_url=image,
                    category=_detect_category(title),
                    hot_score=hot_score,
                    comment_count=comment_count,
                ))
            except Exception as exc:
                self.logger.warning("article_parse_error", error=str(exc))

        return deals
