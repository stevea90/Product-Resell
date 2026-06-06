"""
Scoring Celery tasks.
Runs the profitability calculator + opportunity scoring engine on enriched deals.
Triggers notification if score exceeds threshold.
"""
import asyncio

from sqlalchemy import select

from app.core.config import settings
from app.core.logging import get_logger
from app.db.database import get_db_context
from app.db.models.deal import Deal
from app.db.models.opportunity import Opportunity
from app.db.models.product import AmazonProduct
from app.services.deal_service import DealService
from app.services.scoring.engine import OpportunityScoringEngine
from app.services.scoring.profitability import ProfitabilityCalculator
from app.workers.celery_app import celery_app

logger = get_logger(__name__)


def _run_async(coro):
    async def _with_cleanup():
        try:
            return await coro
        finally:
            from app.db.database import engine
            await engine.dispose()
    return asyncio.run(_with_cleanup())


@celery_app.task(
    name="app.workers.scoring_tasks.score_deal_task",
    bind=True,
    max_retries=2,
    soft_time_limit=120,
)
def score_deal_task(self, deal_id: int):
    """Score a single deal after enrichment. Triggers alert if high score."""
    logger.info("scoring_task_started", deal_id=deal_id, task_id=self.request.id)
    try:
        _run_async(_score_deal(deal_id))
    except Exception as exc:
        logger.error("scoring_task_failed", deal_id=deal_id, error=str(exc))
        raise self.retry(exc=exc)


async def _score_deal(deal_id: int) -> None:
    calculator = ProfitabilityCalculator()
    scorer = OpportunityScoringEngine()

    async with get_db_context() as db:
        # Load deal + Amazon product
        deal_result = await db.execute(select(Deal).where(Deal.id == deal_id))
        deal = deal_result.scalar_one_or_none()
        if not deal:
            logger.warning("score_deal_not_found", deal_id=deal_id)
            return

        amazon_result = await db.execute(
            select(AmazonProduct).where(AmazonProduct.deal_id == deal_id)
        )
        amazon = amazon_result.scalar_one_or_none()
        if not amazon:
            logger.warning("score_no_amazon_product", deal_id=deal_id)
            return

        # Calculate profitability
        from app.services.enrichment.amazon import EnrichedProduct
        enriched = _amazon_model_to_enriched(amazon)

        profit = calculator.calculate(
            deal_price=deal.deal_price or 0,
            amazon_product=enriched,
            category=deal.category.value if deal.category else "other",
        )

        if not profit:
            logger.warning("score_no_profit_result", deal_id=deal_id)
            deal_svc = DealService(db)
            await deal_svc.mark_deal_ignored(deal_id)
            return

        # Score opportunity
        result = await scorer.score(deal, enriched, profit)

        # Filter deals below minimum ROI
        if profit.roi_percent < settings.min_roi_percent:
            deal_svc = DealService(db)
            await deal_svc.mark_deal_ignored(deal_id)
            logger.info(
                "deal_below_min_roi",
                deal_id=deal_id,
                roi=profit.roi_percent,
                threshold=settings.min_roi_percent,
            )
            return

        # Save opportunity
        opportunity = Opportunity(
            deal_id=deal_id,
            buy_price=profit.buy_price,
            sell_price=profit.sell_price,
            gross_profit=profit.gross_profit,
            net_profit=profit.net_profit,
            roi_percent=profit.roi_percent,
            margin_percent=profit.margin_percent,
            break_even_price=profit.break_even_price,
            estimated_payout=profit.estimated_payout,
            amazon_referral_fee=profit.amazon_referral_fee,
            fba_fee=profit.fba_fee,
            vat_amount=profit.vat_amount,
            shipping_cost=profit.inbound_shipping,
            total_costs=profit.total_costs,
            score=result.score,
            confidence_level=result.confidence_level,
            score_roi=result.components.roi,
            score_demand=result.components.demand,
            score_competition=result.components.competition,
            score_reviews=result.components.reviews,
            score_price_stability=result.components.price_stability,
            score_community=result.components.community,
            score_reasoning=result.reasoning,
            tags=",".join(result.tags),
        )
        db.add(opportunity)

        # Mark deal as scored
        deal_svc = DealService(db)
        await deal_svc.mark_deal_scored(deal_id)
        await db.commit()

        logger.info(
            "deal_scored_and_saved",
            deal_id=deal_id,
            score=result.score,
            roi=profit.roi_percent,
            net_profit=profit.net_profit,
        )

    # Trigger alert if score exceeds threshold
    if result.score >= settings.alert_score_threshold:
        from app.workers.notification_tasks import send_opportunity_alert_task
        send_opportunity_alert_task.apply_async(args=[deal_id], countdown=1)


def _amazon_model_to_enriched(amazon: AmazonProduct):
    """Convert AmazonProduct DB model to EnrichedProduct dataclass."""
    from app.services.enrichment.amazon import EnrichedProduct
    return EnrichedProduct(
        asin=amazon.asin,
        amazon_url=amazon.amazon_url,
        title=amazon.title,
        brand=amazon.brand,
        current_price=amazon.current_price,
        buy_box_price=amazon.buy_box_price,
        lowest_price_30d=amazon.lowest_price_30d,
        highest_price_30d=amazon.highest_price_30d,
        lowest_price_90d=amazon.lowest_price_90d,
        buy_box_seller_count=amazon.buy_box_seller_count,
        is_amazon_selling=amazon.is_amazon_selling,
        fba_seller_count=amazon.fba_seller_count,
        sales_rank=amazon.sales_rank,
        sales_rank_category=amazon.sales_rank_category,
        estimated_monthly_sales=amazon.estimated_monthly_sales,
        review_count=amazon.review_count,
        review_rating=amazon.review_rating,
        fba_fee_estimate=amazon.fba_fee_estimate,
        referral_fee_estimate=amazon.referral_fee_estimate,
        referral_fee_percent=amazon.referral_fee_percent,
        weight_kg=amazon.weight_kg,
        data_source=amazon.data_source or "unknown",
        match_confidence=amazon.match_confidence or 0.5,
    )
