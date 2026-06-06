"""
Enrichment Celery tasks.
Picks up PENDING deals and runs Amazon data lookup + scoring pipeline.
"""
import asyncio

from app.core.config import settings
from app.core.logging import get_logger
from app.db.database import get_db_context
from app.db.models.product import AmazonProduct
from app.services.deal_service import DealService
from app.services.enrichment.amazon import AmazonEnrichmentService
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
    name="app.workers.enrichment_tasks.enrich_pending_deals_task",
    bind=True,
    max_retries=2,
    soft_time_limit=600,
)
def enrich_pending_deals_task(self, limit: int = 20):
    """
    Picks up to `limit` PENDING deals and enriches them with Amazon data.
    After enrichment, triggers scoring.
    """
    logger.info("enrichment_task_started", task_id=self.request.id)
    try:
        _run_async(_enrich_pending(limit))
    except Exception as exc:
        logger.error("enrichment_task_failed", error=str(exc))
        raise self.retry(exc=exc)


async def _enrich_pending(limit: int) -> None:
    enricher = AmazonEnrichmentService()
    try:
        async with get_db_context() as db:
            deal_svc = DealService(db)
            pending_deals = await deal_svc.get_pending_deals(limit=limit)

        logger.info("enriching_deals", count=len(pending_deals))

        for deal in pending_deals:
            try:
                async with get_db_context() as db:
                    deal_svc = DealService(db)
                    await deal_svc.mark_deal_enriching(deal.id)

                amazon_data = await enricher.enrich(deal)

                if not amazon_data:
                    async with get_db_context() as db:
                        deal_svc = DealService(db)
                        await deal_svc.mark_deal_ignored(deal.id)
                    logger.info("deal_no_match", deal_id=deal.id)
                    continue

                # Check minimum ROI before saving
                if (
                    amazon_data.current_price
                    and deal.deal_price
                    and amazon_data.current_price <= deal.deal_price
                ):
                    async with get_db_context() as db:
                        deal_svc = DealService(db)
                        await deal_svc.mark_deal_ignored(deal.id)
                    logger.info("deal_below_cost", deal_id=deal.id)
                    continue

                # Persist Amazon product data
                async with get_db_context() as db:
                    amazon_product = AmazonProduct(
                        deal_id=deal.id,
                        asin=amazon_data.asin,
                        amazon_url=amazon_data.amazon_url,
                        title=amazon_data.title,
                        brand=amazon_data.brand,
                        current_price=amazon_data.current_price,
                        lowest_price_30d=amazon_data.lowest_price_30d,
                        highest_price_30d=amazon_data.highest_price_30d,
                        lowest_price_90d=amazon_data.lowest_price_90d,
                        buy_box_price=amazon_data.buy_box_price,
                        buy_box_seller_count=amazon_data.buy_box_seller_count,
                        is_amazon_selling=amazon_data.is_amazon_selling,
                        fba_seller_count=amazon_data.fba_seller_count,
                        sales_rank=amazon_data.sales_rank,
                        sales_rank_category=amazon_data.sales_rank_category,
                        estimated_monthly_sales=amazon_data.estimated_monthly_sales,
                        review_count=amazon_data.review_count,
                        review_rating=amazon_data.review_rating,
                        fba_fee_estimate=amazon_data.fba_fee_estimate,
                        referral_fee_estimate=amazon_data.referral_fee_estimate,
                        referral_fee_percent=amazon_data.referral_fee_percent,
                        weight_kg=amazon_data.weight_kg,
                        data_source=amazon_data.data_source,
                        match_confidence=amazon_data.match_confidence,
                    )
                    db.add(amazon_product)
                    await db.commit()

                # Queue scoring
                from app.workers.scoring_tasks import score_deal_task
                score_deal_task.apply_async(args=[deal.id], countdown=2)

                logger.info(
                    "deal_enriched",
                    deal_id=deal.id,
                    asin=amazon_data.asin,
                    price=amazon_data.current_price,
                )

            except Exception as exc:
                logger.error("deal_enrichment_error", deal_id=deal.id, error=str(exc))
    finally:
        await enricher.close()
