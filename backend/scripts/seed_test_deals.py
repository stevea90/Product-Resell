"""
Seed the database with realistic test deals that have already been scored.
Run this inside the backend container to instantly populate the dashboard:

    docker compose exec backend python scripts/seed_test_deals.py

This is useful when Amazon scraping is blocked and you want to verify the
full UI pipeline (deals list, filtering, opportunity cards) without waiting
for live enrichment.
"""
import asyncio
import sys
from datetime import datetime, timezone

sys.path.insert(0, "/app")

from sqlalchemy import text
from app.db.database import get_db_context
from app.db.models.deal import Deal, DealSource, DealCategory, DealStatus
from app.db.models.opportunity import Opportunity
from app.db.models.product import AmazonProduct

_TEST_DEALS = [
    {
        "deal": dict(
            title="LEGO Technic Land Rover Defender 42110 — £160 at Smyths",
            source=DealSource.HOTUKDEALS,
            source_url="https://www.hotukdeals.com/deals/lego-technic-land-rover-defender-42110",
            deal_price=160.00,
            original_price=199.99,
            discount_percent=20.0,
            category=DealCategory.TOYS,
            status=DealStatus.SCORED,
            hot_score=312,
        ),
        "amazon": dict(
            asin="B07SDZQS1R",
            amazon_url="https://www.amazon.co.uk/dp/B07SDZQS1R",
            title="LEGO 42110 Technic Land Rover Defender",
            brand="LEGO",
            current_price=219.99,
            buy_box_price=219.99,
            lowest_price_30d=199.99,
            highest_price_30d=249.99,
            lowest_price_90d=189.99,
            buy_box_seller_count=3,
            is_amazon_selling=False,
            fba_seller_count=5,
            sales_rank=850,
            sales_rank_category="Toys & Games",
            estimated_monthly_sales=1500,
            review_count=4821,
            review_rating=4.8,
            fba_fee_estimate=6.50,
            referral_fee_percent=0.08,
            referral_fee_estimate=17.60,
            weight_kg=2.1,
            data_source="seeded",
            match_confidence=0.95,
        ),
        "opportunity": dict(
            buy_price=160.00,
            sell_price=219.99,
            gross_profit=59.99,
            net_profit=31.24,
            roi_percent=19.53,
            margin_percent=14.20,
            break_even_price=188.75,
            estimated_payout=195.74,
            amazon_referral_fee=17.60,
            fba_fee=6.50,
            vat_amount=0.0,
            shipping_cost=1.68,
            total_costs=25.78,
            score=82,
            confidence_level="high",
            score_roi=78,
            score_demand=90,
            score_competition=85,
            score_reviews=95,
            score_price_stability=72,
            score_community=88,
            score_reasoning=(
                "Strong seller with 4,800+ reviews and consistent BSR under 1,000. "
                "LEGO holds value well — 90-day low confirms floor. "
                "3 FBA competitors keeps margin healthy."
            ),
            tags="lego,toys,fba-eligible,high-demand",
        ),
    },
    {
        "deal": dict(
            title="Nintendo Switch OLED — £279.99 at Currys (was £309.99)",
            source=DealSource.HOTUKDEALS,
            source_url="https://www.hotukdeals.com/deals/nintendo-switch-oled-currys",
            deal_price=279.99,
            original_price=309.99,
            discount_percent=10.0,
            category=DealCategory.GAMING,
            status=DealStatus.SCORED,
            hot_score=547,
        ),
        "amazon": dict(
            asin="B09HGNPKGR",
            amazon_url="https://www.amazon.co.uk/dp/B09HGNPKGR",
            title="Nintendo Switch OLED Model — White",
            brand="Nintendo",
            current_price=319.99,
            buy_box_price=309.99,
            lowest_price_30d=299.99,
            highest_price_30d=334.99,
            lowest_price_90d=289.99,
            buy_box_seller_count=7,
            is_amazon_selling=True,
            fba_seller_count=12,
            sales_rank=45,
            sales_rank_category="PC & Video Games",
            estimated_monthly_sales=4200,
            review_count=12450,
            review_rating=4.7,
            fba_fee_estimate=5.20,
            referral_fee_percent=0.08,
            referral_fee_estimate=24.80,
            weight_kg=0.42,
            data_source="seeded",
            match_confidence=0.97,
        ),
        "opportunity": dict(
            buy_price=279.99,
            sell_price=309.99,
            gross_profit=30.00,
            net_profit=0.00,
            roi_percent=0.0,
            margin_percent=0.0,
            break_even_price=309.99,
            estimated_payout=279.99,
            amazon_referral_fee=24.80,
            fba_fee=5.20,
            vat_amount=0.0,
            shipping_cost=0.34,
            total_costs=30.34,
            score=61,
            confidence_level="medium",
            score_roi=35,
            score_demand=98,
            score_competition=42,
            score_reviews=95,
            score_price_stability=68,
            score_community=92,
            score_reasoning=(
                "Massive demand (rank #45) but Amazon itself is selling — "
                "margin is very thin. Good to watch for price spikes around Christmas."
            ),
            tags="gaming,nintendo,amazon-competing,watch",
        ),
    },
    {
        "deal": dict(
            title="Dyson V15 Detect Absolute Vacuum — £399 at Argos (was £649)",
            source=DealSource.HOTUKDEALS,
            source_url="https://www.hotukdeals.com/deals/dyson-v15-detect-argos-399",
            deal_price=399.00,
            original_price=649.00,
            discount_percent=38.5,
            category=DealCategory.ELECTRONICS,
            status=DealStatus.SCORED,
            hot_score=891,
        ),
        "amazon": dict(
            asin="B08R68LMVJ",
            amazon_url="https://www.amazon.co.uk/dp/B08R68LMVJ",
            title="Dyson V15 Detect Absolute Cordless Vacuum Cleaner",
            brand="Dyson",
            current_price=549.00,
            buy_box_price=529.99,
            lowest_price_30d=499.00,
            highest_price_30d=649.00,
            lowest_price_90d=479.00,
            buy_box_seller_count=2,
            is_amazon_selling=False,
            fba_seller_count=4,
            sales_rank=1240,
            sales_rank_category="Home & Kitchen",
            estimated_monthly_sales=820,
            review_count=9340,
            review_rating=4.6,
            fba_fee_estimate=9.80,
            referral_fee_percent=0.15,
            referral_fee_estimate=79.50,
            weight_kg=2.9,
            data_source="seeded",
            match_confidence=0.93,
        ),
        "opportunity": dict(
            buy_price=399.00,
            sell_price=529.99,
            gross_profit=130.99,
            net_profit=39.37,
            roi_percent=9.87,
            margin_percent=7.43,
            break_even_price=488.30,
            estimated_payout=440.69,
            amazon_referral_fee=79.50,
            fba_fee=9.80,
            vat_amount=0.0,
            shipping_cost=2.32,
            total_costs=91.62,
            score=88,
            confidence_level="high",
            score_roi=88,
            score_demand=80,
            score_competition=90,
            score_reviews=92,
            score_price_stability=85,
            score_community=95,
            score_reasoning=(
                "Exceptional £130 gross profit margin on a premium Dyson. "
                "Only 2 buy-box sellers and Amazon not competing. "
                "38% discount vs RRP creates strong arbitrage window."
            ),
            tags="electronics,dyson,premium,high-margin,fba-eligible",
        ),
    },
    {
        "deal": dict(
            title="PlayStation 5 Slim Disc Edition — £399.99 at GAME",
            source=DealSource.HOTUKDEALS,
            source_url="https://www.hotukdeals.com/deals/ps5-slim-disc-game-399",
            deal_price=399.99,
            original_price=449.99,
            discount_percent=11.0,
            category=DealCategory.GAMING,
            status=DealStatus.SCORED,
            hot_score=1203,
        ),
        "amazon": dict(
            asin="B0CL61F39H",
            amazon_url="https://www.amazon.co.uk/dp/B0CL61F39H",
            title="PlayStation 5 Slim Console (Disc Edition)",
            brand="Sony",
            current_price=449.99,
            buy_box_price=449.99,
            lowest_price_30d=429.99,
            highest_price_30d=499.99,
            lowest_price_90d=419.99,
            buy_box_seller_count=9,
            is_amazon_selling=True,
            fba_seller_count=18,
            sales_rank=22,
            sales_rank_category="PC & Video Games",
            estimated_monthly_sales=5000,
            review_count=3280,
            review_rating=4.5,
            fba_fee_estimate=6.20,
            referral_fee_percent=0.08,
            referral_fee_estimate=36.00,
            weight_kg=3.2,
            data_source="seeded",
            match_confidence=0.98,
        ),
        "opportunity": dict(
            buy_price=399.99,
            sell_price=449.99,
            gross_profit=50.00,
            net_profit=5.24,
            roi_percent=1.31,
            margin_percent=1.16,
            break_even_price=444.75,
            estimated_payout=407.79,
            amazon_referral_fee=36.00,
            fba_fee=6.20,
            vat_amount=0.0,
            shipping_cost=2.56,
            total_costs=44.76,
            score=55,
            confidence_level="low",
            score_roi=20,
            score_demand=99,
            score_competition=30,
            score_reviews=82,
            score_price_stability=60,
            score_community=98,
            score_reasoning=(
                "Enormous demand but Amazon competes directly and 9 buy-box sellers "
                "compress margins to almost zero. Wait for stock shortage events."
            ),
            tags="gaming,sony,ps5,amazon-competing,thin-margin",
        ),
    },
    {
        "deal": dict(
            title="Pokémon Scarlet & Violet — 151 Ultra Premium Collection Box",
            source=DealSource.HOTUKDEALS,
            source_url="https://www.hotukdeals.com/deals/pokemon-151-ultra-premium-collection",
            deal_price=89.99,
            original_price=129.99,
            discount_percent=31.0,
            category=DealCategory.TOYS,
            status=DealStatus.SCORED,
            hot_score=674,
        ),
        "amazon": dict(
            asin="B0CGMFJ12M",
            amazon_url="https://www.amazon.co.uk/dp/B0CGMFJ12M",
            title="Pokémon 151 Ultra Premium Collection Box",
            brand="Pokémon",
            current_price=169.99,
            buy_box_price=164.99,
            lowest_price_30d=149.99,
            highest_price_30d=219.99,
            lowest_price_90d=139.99,
            buy_box_seller_count=2,
            is_amazon_selling=False,
            fba_seller_count=3,
            sales_rank=320,
            sales_rank_category="Toys & Games",
            estimated_monthly_sales=2800,
            review_count=1876,
            review_rating=4.9,
            fba_fee_estimate=4.80,
            referral_fee_percent=0.08,
            referral_fee_estimate=13.20,
            weight_kg=0.92,
            data_source="seeded",
            match_confidence=0.91,
        ),
        "opportunity": dict(
            buy_price=89.99,
            sell_price=164.99,
            gross_profit=75.00,
            net_profit=55.26,
            roi_percent=61.41,
            margin_percent=33.49,
            break_even_price=108.05,
            estimated_payout=146.99,
            amazon_referral_fee=13.20,
            fba_fee=4.80,
            vat_amount=0.0,
            shipping_cost=0.74,
            total_costs=18.74,
            score=94,
            confidence_level="high",
            score_roi=98,
            score_demand=92,
            score_competition=95,
            score_reviews=98,
            score_price_stability=78,
            score_community=90,
            score_reasoning=(
                "Outstanding 61% ROI on limited Pokémon collector set. "
                "Only 2 buy-box sellers, Amazon not competing, rank #320. "
                "Pokémon 151 is a highly sought collector's item with strong price floor."
            ),
            tags="pokemon,toys,collector,high-roi,limited-stock,fba-eligible",
        ),
    },
]


async def seed() -> None:
    async with get_db_context() as db:
        # Check if already seeded
        from sqlalchemy import select, func
        count_result = await db.execute(select(func.count()).select_from(Deal).where(Deal.status == DealStatus.SCORED))
        existing = count_result.scalar()
        if existing and existing >= 3:
            print(f"Database already has {existing} scored deals — skipping seed.")
            return

        inserted = 0
        for entry in _TEST_DEALS:
            deal_data = entry["deal"]
            amazon_data = entry["amazon"]
            opp_data = entry["opportunity"]

            deal = Deal(
                **deal_data,
                deal_posted_at=datetime.now(timezone.utc),
            )
            db.add(deal)
            await db.flush()  # get deal.id

            amazon = AmazonProduct(deal_id=deal.id, **amazon_data)
            db.add(amazon)

            opp = Opportunity(deal_id=deal.id, **opp_data)
            db.add(opp)

            inserted += 1

        await db.commit()
        print(f"Seeded {inserted} test deals with opportunities.")


if __name__ == "__main__":
    asyncio.run(seed())
