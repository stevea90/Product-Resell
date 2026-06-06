"""
Unit tests for the opportunity scoring engine.
Validates that each scoring component produces expected ranges.
"""
import asyncio
from unittest.mock import MagicMock

import pytest

from app.db.models.deal import Deal, DealCategory, DealSource, DealStatus
from app.services.enrichment.amazon import EnrichedProduct
from app.services.scoring.engine import OpportunityScoringEngine
from app.services.scoring.profitability import ProfitabilityResult


def make_deal(**overrides) -> Deal:
    d = MagicMock(spec=Deal)
    d.id = 1
    d.source = DealSource.HOTUKDEALS
    d.title = "LEGO Technic Bugatti 42083"
    d.category = DealCategory.LEGO
    d.deal_price = 89.99
    d.hot_score = 350
    d.comment_count = 45
    d.discount_percent = 40.0
    for k, v in overrides.items():
        setattr(d, k, v)
    return d


def make_amazon(**overrides) -> EnrichedProduct:
    defaults = dict(
        asin="B07FDCHF9V",
        amazon_url="https://www.amazon.co.uk/dp/B07FDCHF9V",
        title="LEGO Technic 42083",
        brand="LEGO",
        current_price=149.99,
        buy_box_price=149.99,
        lowest_price_30d=145.00,
        highest_price_30d=155.00,
        lowest_price_90d=140.00,
        buy_box_seller_count=2,
        is_amazon_selling=False,
        fba_seller_count=2,
        sales_rank=800,
        sales_rank_category="Toys & Games",
        estimated_monthly_sales=400,
        review_count=320,
        review_rating=4.8,
        fba_fee_estimate=5.75,
        referral_fee_estimate=22.50,
        referral_fee_percent=0.15,
        weight_kg=2.0,
        data_source="keepa",
        match_confidence=0.95,
    )
    defaults.update(overrides)
    return EnrichedProduct(**defaults)


def make_profit(**overrides) -> ProfitabilityResult:
    defaults = dict(
        buy_price=89.99,
        sell_price=149.99,
        amazon_referral_fee=22.50,
        fba_fee=5.75,
        inbound_shipping=1.60,
        total_costs=29.85,
        gross_profit=60.00,
        net_profit=30.15,
        roi_percent=33.5,
        margin_percent=20.1,
        break_even_price=119.84,
        estimated_payout=121.74,
        weight_kg=2.0,
        referral_fee_percent=0.15,
        vat_amount=0.0,
    )
    defaults.update(overrides)
    return ProfitabilityResult(**defaults)


class TestOpportunityScoringEngine:
    def setup_method(self):
        self.engine = OpportunityScoringEngine()

    def _score(self, deal=None, amazon=None, profit=None):
        d = deal or make_deal()
        a = amazon or make_amazon()
        p = profit or make_profit()
        return asyncio.get_event_loop().run_until_complete(
            self.engine.score(d, a, p)
        )

    def test_high_quality_deal_scores_above_70(self):
        result = self._score()
        assert result.score >= 70

    def test_amazon_selling_reduces_score(self):
        """If Amazon itself is a seller, competition score should tank."""
        amazon_no_amz = make_amazon(is_amazon_selling=False, buy_box_seller_count=2)
        amazon_with_amz = make_amazon(is_amazon_selling=True, buy_box_seller_count=2)

        score_no_amz = self._score(amazon=amazon_no_amz)
        score_with_amz = self._score(amazon=amazon_with_amz)

        assert score_with_amz.score < score_no_amz.score
        assert score_with_amz.components.competition <= 3

    def test_very_low_roi_scores_low(self):
        profit = make_profit(roi_percent=5.0, net_profit=2.00)
        result = self._score(profit=profit)
        assert result.components.roi < 5

    def test_high_roi_maxes_roi_component(self):
        profit = make_profit(roi_percent=80.0, net_profit=50.00)
        result = self._score(profit=profit)
        assert result.components.roi >= 22

    def test_no_community_signals_reduces_score(self):
        deal_cold = make_deal(hot_score=0, comment_count=0)
        deal_hot = make_deal(hot_score=500, comment_count=80)

        result_cold = self._score(deal=deal_cold)
        result_hot = self._score(deal=deal_hot)

        assert result_hot.components.community > result_cold.components.community

    def test_score_total_within_bounds(self):
        result = self._score()
        assert 0 <= result.score <= 100

    def test_confidence_level_correct(self):
        result = self._score()
        assert result.confidence_level in ("low", "medium", "high", "very_high")

    def test_tags_generated(self):
        result = self._score()
        assert isinstance(result.tags, list)
        assert len(result.tags) > 0

    def test_reasoning_non_empty(self):
        result = self._score()
        assert result.reasoning and len(result.reasoning) > 10

    def test_volatile_price_reduces_stability_score(self):
        stable = make_amazon(
            current_price=40.00, lowest_price_30d=38.00, highest_price_30d=42.00
        )
        volatile = make_amazon(
            current_price=40.00, lowest_price_30d=20.00, highest_price_30d=60.00
        )

        stable_result = self._score(amazon=stable)
        volatile_result = self._score(amazon=volatile)

        assert stable_result.components.price_stability > volatile_result.components.price_stability
