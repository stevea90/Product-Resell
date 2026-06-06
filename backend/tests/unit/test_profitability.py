"""
Unit tests for the profitability calculator.
These run without any external services or DB.
"""
import pytest
from unittest.mock import MagicMock

from app.services.enrichment.amazon import EnrichedProduct
from app.services.scoring.profitability import ProfitabilityCalculator


def make_amazon_product(**overrides) -> EnrichedProduct:
    defaults = dict(
        asin="B08XYZ1234",
        amazon_url="https://www.amazon.co.uk/dp/B08XYZ1234",
        title="Test Product",
        brand="TestBrand",
        current_price=39.99,
        buy_box_price=39.99,
        lowest_price_30d=37.00,
        highest_price_30d=42.00,
        lowest_price_90d=35.00,
        buy_box_seller_count=3,
        is_amazon_selling=False,
        fba_seller_count=2,
        sales_rank=5000,
        sales_rank_category="Toys & Games",
        estimated_monthly_sales=200,
        review_count=150,
        review_rating=4.4,
        fba_fee_estimate=3.50,
        referral_fee_estimate=6.00,
        referral_fee_percent=0.15,
        weight_kg=0.5,
        data_source="keepa",
        match_confidence=0.9,
    )
    defaults.update(overrides)
    return EnrichedProduct(**defaults)


class TestProfitabilityCalculator:
    def setup_method(self):
        self.calc = ProfitabilityCalculator()

    def test_basic_profitable_deal(self):
        amazon = make_amazon_product(buy_box_price=39.99, fba_fee_estimate=3.50)
        result = self.calc.calculate(
            deal_price=19.99,
            amazon_product=amazon,
            category="toys",
        )

        assert result is not None
        assert result.is_profitable
        assert result.buy_price == pytest.approx(19.99, abs=0.01)
        assert result.sell_price == pytest.approx(39.99, abs=0.01)
        assert result.roi_percent > 0
        assert result.net_profit > 0

    def test_loss_making_deal(self):
        """Deal price higher than Amazon sell price → not profitable."""
        amazon = make_amazon_product(buy_box_price=15.00)
        result = self.calc.calculate(
            deal_price=18.00,
            amazon_product=amazon,
            category="toys",
        )
        assert result is not None
        assert not result.is_profitable
        assert result.net_profit < 0

    def test_referral_fee_deducted(self):
        """Referral fee should be 15% of sell price for toys."""
        amazon = make_amazon_product(buy_box_price=40.00, referral_fee_percent=0.15)
        result = self.calc.calculate(deal_price=20.00, amazon_product=amazon, category="toys")

        assert result is not None
        expected_referral = 40.00 * 0.15
        assert result.amazon_referral_fee == pytest.approx(expected_referral, abs=0.01)

    def test_gaming_lower_referral_fee(self):
        """Gaming category has 7% referral fee, not 15%."""
        amazon = make_amazon_product(
            buy_box_price=60.00,
            referral_fee_percent=0.07,
            fba_fee_estimate=3.50,
        )
        result = self.calc.calculate(deal_price=30.00, amazon_product=amazon, category="gaming")

        assert result is not None
        assert result.amazon_referral_fee == pytest.approx(60.00 * 0.07, abs=0.01)

    def test_break_even_price_above_buy_price(self):
        """Break-even should always be higher than buy price (it includes fees)."""
        amazon = make_amazon_product(buy_box_price=50.00)
        result = self.calc.calculate(deal_price=25.00, amazon_product=amazon)

        assert result is not None
        assert result.break_even_price > result.buy_price

    def test_roi_calculation(self):
        """Verify ROI formula: net_profit / buy_price * 100."""
        amazon = make_amazon_product(
            buy_box_price=40.00,
            fba_fee_estimate=3.50,
            referral_fee_percent=0.15,
        )
        result = self.calc.calculate(deal_price=20.00, amazon_product=amazon, category="toys")
        assert result is not None

        expected_roi = (result.net_profit / result.buy_price) * 100
        assert result.roi_percent == pytest.approx(expected_roi, abs=0.1)

    def test_missing_sell_price_returns_none(self):
        """Should return None if we can't determine a sell price."""
        amazon = make_amazon_product(current_price=None, buy_box_price=None)
        result = self.calc.calculate(deal_price=20.00, amazon_product=amazon)
        assert result is None

    def test_shipping_cost_included(self):
        """Inbound shipping should be included in total costs."""
        amazon = make_amazon_product(buy_box_price=40.00, weight_kg=1.0)
        result = self.calc.calculate(deal_price=20.00, amazon_product=amazon)

        assert result is not None
        assert result.inbound_shipping > 0
        assert result.total_costs == pytest.approx(
            result.amazon_referral_fee + result.fba_fee + result.inbound_shipping,
            abs=0.01,
        )
