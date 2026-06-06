"""
Profitability calculator for Amazon FBA resale.

All monetary values in GBP.

FBA cost structure:
  Revenue = Buy Box price (what customer pays)
  - Amazon referral fee (% of revenue, varies by category)
  - FBA fulfilment fee (per unit, based on size/weight tier)
  - Inbound shipping (per kg, from retailer to FBA warehouse)
  ──────────────────────────────
  = Estimated payout (before cost of goods)
  - Cost of goods (deal price, already incl. VAT)
  ──────────────────────────────
  = Net profit

ROI = net_profit / buy_price * 100
Margin = net_profit / sell_price * 100

Break-even price = total_costs (fees + shipping + cost of goods)

VAT treatment: UK retailers charge VAT at 20%. As a private seller / small
business you generally cannot reclaim VAT unless VAT-registered and selling
in a VAT-qualifying category. The calculator assumes you're paying VAT-inclusive
retail price and selling at Amazon's consumer price (which is VAT-inclusive for
most toy/electronic categories). Adjust vat_reclaim=True if applicable.
"""
from dataclasses import dataclass, field
from typing import Optional

from app.core.config import settings
from app.services.enrichment.amazon import EnrichedProduct


# ── Amazon FBA fee tiers (approximate UK rates as of 2024) ───────────────────
# These are simplified; real rates depend on exact product dimensions.
# Source: https://sellercentral.amazon.co.uk/gp/help/G200336920

FBA_FEE_TIERS = [
    # (max_weight_kg, fee_gbp) — sorted ascending
    (0.25, 2.70),
    (0.50, 3.05),
    (1.00, 3.50),
    (2.00, 4.30),
    (5.00, 5.75),
    (10.00, 7.90),
    (20.00, 11.25),
    (30.00, 14.50),
]

# Referral fee by category (% of sale price)
REFERRAL_FEES_BY_CATEGORY = {
    "toys": 0.15,
    "lego": 0.15,
    "gaming": 0.07,  # Video games have lower referral fee
    "electronics": 0.07,
    "other": 0.15,
}


@dataclass
class ProfitabilityResult:
    """Full profitability breakdown for one deal."""

    # Input
    buy_price: float
    sell_price: float

    # Fee components
    amazon_referral_fee: float
    fba_fee: float
    inbound_shipping: float
    total_costs: float

    # Profit metrics
    gross_profit: float      # sell_price - buy_price
    net_profit: float        # sell_price - total_costs - buy_price
    roi_percent: float       # net_profit / buy_price * 100
    margin_percent: float    # net_profit / sell_price * 100
    break_even_price: float  # buy_price + total_fees
    estimated_payout: float  # sell_price - amazon_referral_fee - fba_fee

    # Assumptions used
    weight_kg: float
    referral_fee_percent: float
    vat_amount: float = 0.0

    # Quick verdict
    is_profitable: bool = field(init=False)

    def __post_init__(self) -> None:
        self.is_profitable = self.net_profit > 0

    def summary(self) -> str:
        return (
            f"Buy £{self.buy_price:.2f} → Sell £{self.sell_price:.2f} | "
            f"Net profit: £{self.net_profit:.2f} | "
            f"ROI: {self.roi_percent:.1f}% | "
            f"Margin: {self.margin_percent:.1f}%"
        )


class ProfitabilityCalculator:
    """
    Calculates profitability for a deal given its deal price and
    the Amazon enrichment data.

    All assumptions come from settings and can be overridden per-call.
    """

    def __init__(self) -> None:
        self.vat_rate = settings.vat_rate
        self.shipping_per_kg = settings.shipping_cost_per_kg_gbp
        self.default_weight_kg = settings.default_product_weight_kg

    def calculate(
        self,
        deal_price: float,
        amazon_product: EnrichedProduct,
        category: str = "other",
        weight_kg: Optional[float] = None,
        vat_reclaim: bool = False,
    ) -> Optional[ProfitabilityResult]:
        """
        Calculate profitability. Returns None if we lack the sell price.
        """
        # Determine sell price — use buy box price as the expected selling price
        sell_price = amazon_product.buy_box_price or amazon_product.current_price
        if not sell_price or not deal_price:
            return None

        # Effective buy price (what we pay at the retailer)
        buy_price = round(deal_price, 2)

        # VAT: UK retail prices already include VAT. We normally can't reclaim.
        # If vat_reclaim=True (VAT-registered), we reclaim the VAT portion.
        vat_amount = 0.0
        effective_buy_price = buy_price
        if vat_reclaim:
            vat_amount = round(buy_price * self.vat_rate / (1 + self.vat_rate), 2)
            effective_buy_price = round(buy_price - vat_amount, 2)

        # Weight — prefer enrichment data, fall back to default
        effective_weight = weight_kg or amazon_product.weight_kg or self.default_weight_kg

        # FBA fulfilment fee
        fba_fee = self._fba_fee(effective_weight)
        if amazon_product.fba_fee_estimate:
            # Trust Keepa's estimate if available
            fba_fee = amazon_product.fba_fee_estimate

        # Referral fee
        ref_pct = (
            amazon_product.referral_fee_percent
            or REFERRAL_FEES_BY_CATEGORY.get(category, 0.15)
        )
        referral_fee = round(sell_price * ref_pct, 2)

        # Inbound shipping to FBA warehouse
        inbound_shipping = round(effective_weight * self.shipping_per_kg, 2)

        # Total Amazon-side costs
        total_fees = round(fba_fee + referral_fee, 2)
        total_costs = round(total_fees + inbound_shipping, 2)

        # Estimated payout from Amazon
        estimated_payout = round(sell_price - total_fees, 2)

        # Profit
        gross_profit = round(sell_price - effective_buy_price, 2)
        net_profit = round(estimated_payout - effective_buy_price - inbound_shipping, 2)
        roi_percent = round((net_profit / effective_buy_price) * 100, 2) if effective_buy_price > 0 else 0.0
        margin_percent = round((net_profit / sell_price) * 100, 2) if sell_price > 0 else 0.0
        break_even_price = round(effective_buy_price + total_costs, 2)

        return ProfitabilityResult(
            buy_price=effective_buy_price,
            sell_price=sell_price,
            amazon_referral_fee=referral_fee,
            fba_fee=fba_fee,
            inbound_shipping=inbound_shipping,
            total_costs=total_costs,
            gross_profit=gross_profit,
            net_profit=net_profit,
            roi_percent=roi_percent,
            margin_percent=margin_percent,
            break_even_price=break_even_price,
            estimated_payout=estimated_payout,
            weight_kg=effective_weight,
            referral_fee_percent=ref_pct,
            vat_amount=vat_amount,
        )

    def _fba_fee(self, weight_kg: float) -> float:
        """Look up FBA fee by weight tier."""
        for max_weight, fee in FBA_FEE_TIERS:
            if weight_kg <= max_weight:
                return fee
        # Oversize / heavy — use highest tier as minimum
        return FBA_FEE_TIERS[-1][1]
