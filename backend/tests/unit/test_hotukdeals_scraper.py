"""
Unit tests for the HotUKDeals scraper.
Uses fixture RSS XML — no real HTTP calls.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.scrapers.hotukdeals import (
    HotUKDealsScraper,
    _detect_category,
    _extract_price,
)


SAMPLE_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>hotukdeals</title>
    <item>
      <title>LEGO Star Wars Millennium Falcon 75192 - £699.99 (was £849.99) @ Amazon</title>
      <link>https://www.hotukdeals.com/deals/lego-star-wars-1234567</link>
      <guid>https://www.hotukdeals.com/deals/lego-star-wars-1234567</guid>
      <pubDate>Fri, 06 Jun 2025 09:00:00 +0000</pubDate>
      <description>
        &lt;img src="https://img.hotukdeals.com/images/lego.jpg"/&gt;
        &lt;p&gt;Massive LEGO deal from Amazon. Temperature: 523°. 34 comments.&lt;/p&gt;
      </description>
    </item>
    <item>
      <title>PlayStation 5 Console - £449.99 @ Currys</title>
      <link>https://www.hotukdeals.com/deals/ps5-console-7654321</link>
      <guid>https://www.hotukdeals.com/deals/ps5-console-7654321</guid>
      <pubDate>Fri, 06 Jun 2025 10:00:00 +0000</pubDate>
      <description>
        &lt;p&gt;PS5 back in stock at Currys. Temperature: 89°.&lt;/p&gt;
      </description>
    </item>
    <item>
      <title>Random furniture deal</title>
      <link>https://www.hotukdeals.com/deals/furniture-9999999</link>
      <guid>https://www.hotukdeals.com/deals/furniture-9999999</guid>
      <pubDate>Fri, 06 Jun 2025 11:00:00 +0000</pubDate>
      <description>&lt;p&gt;Some sofa on sale.&lt;/p&gt;</description>
    </item>
  </channel>
</rss>"""


class TestCategoryDetection:
    def test_lego_detected(self):
        assert _detect_category("LEGO Star Wars Millennium Falcon 75192") == "lego"

    def test_gaming_detected(self):
        assert _detect_category("PlayStation 5 Console DualSense Controller") == "gaming"

    def test_electronics_detected(self):
        assert _detect_category("Samsung 65 inch 4K QLED TV") == "electronics"

    def test_toys_detected(self):
        assert _detect_category("Nerf Elite 2.0 Blaster Set") == "toys"

    def test_unknown_returns_other(self):
        assert _detect_category("3-seater sofa in grey fabric") == "other"

    def test_case_insensitive(self):
        assert _detect_category("NERF GUN") == "toys"
        assert _detect_category("lego technic") == "lego"


class TestPriceExtraction:
    def test_simple_price(self):
        assert _extract_price("£12.99") == 12.99

    def test_price_in_text(self):
        assert _extract_price("Was £24.99, now £12.99") == 24.99  # First match

    def test_price_with_comma(self):
        assert _extract_price("£1,299.00") == 1299.00

    def test_no_price_returns_none(self):
        assert _extract_price("No price here") is None

    def test_empty_returns_none(self):
        assert _extract_price("") is None


class TestHotUKDealsRSSParser:
    def setup_method(self):
        self.scraper = HotUKDealsScraper()

    def test_parses_lego_deal(self):
        deals = self.scraper._parse_rss_feed(SAMPLE_RSS, "test")

        lego_deals = [d for d in deals if "lego" in d.title.lower() or "lego" in d.source_url]
        assert len(lego_deals) >= 1

        lego = lego_deals[0]
        assert lego.source == "hotukdeals"
        assert lego.source_url == "https://www.hotukdeals.com/deals/lego-star-wars-1234567"

    def test_category_assigned(self):
        deals = self.scraper._parse_rss_feed(SAMPLE_RSS, "test")
        titled = {d.title: d for d in deals}

        lego_deal = next((d for d in deals if "lego" in d.title.lower()), None)
        assert lego_deal is not None
        assert lego_deal.category == "lego"

        ps5_deal = next((d for d in deals if "PlayStation" in d.title), None)
        assert ps5_deal is not None
        assert ps5_deal.category == "gaming"

    def test_source_id_extracted(self):
        deals = self.scraper._parse_rss_feed(SAMPLE_RSS, "test")
        lego_deal = next((d for d in deals if "lego" in d.title.lower()), None)
        assert lego_deal is not None
        assert lego_deal.source_id is not None

    def test_hot_score_parsed(self):
        deals = self.scraper._parse_rss_feed(SAMPLE_RSS, "test")
        lego_deal = next((d for d in deals if "lego" in d.title.lower()), None)
        assert lego_deal is not None
        assert lego_deal.hot_score == 523

    def test_deals_with_unknown_category_still_parsed(self):
        """Furniture deal should parse but category = 'other'."""
        deals = self.scraper._parse_rss_feed(SAMPLE_RSS, "test")
        furniture = next((d for d in deals if "furniture" in d.source_url), None)
        assert furniture is not None
        assert furniture.category == "other"
