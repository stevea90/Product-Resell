"""
Scraping Celery tasks.
Each task runs a scraper, persists results, then triggers enrichment.
"""
import asyncio
from datetime import datetime

from app.core.logging import get_logger
from app.db.database import get_db_context
from app.services.deal_service import DealService
from app.services.scrapers import SCRAPER_REGISTRY
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
    name="app.workers.scraping_tasks.scrape_hotukdeals_task",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    soft_time_limit=300,
)
def scrape_hotukdeals_task(self):
    """
    Scrape HotUKDeals RSS feeds, persist new deals, queue enrichment.
    Retries up to 3 times on failure with 60-second delay.
    """
    logger.info("scrape_task_started", source="hotukdeals", task_id=self.request.id)
    try:
        _run_async(_scrape_and_save("hotukdeals"))
    except Exception as exc:
        logger.error("scrape_task_failed", source="hotukdeals", error=str(exc))
        raise self.retry(exc=exc)


@celery_app.task(
    name="app.workers.scraping_tasks.scrape_all_task",
    bind=True,
)
def scrape_all_task(self):
    """Trigger scraping for all registered sources."""
    for source_name in SCRAPER_REGISTRY:
        celery_app.send_task(
            f"app.workers.scraping_tasks.scrape_{source_name}_task",
        )


async def _scrape_and_save(source_name: str) -> None:
    """Async implementation: runs scraper → persists → queues enrichment."""
    scraper_cls = SCRAPER_REGISTRY.get(source_name)
    if not scraper_cls:
        logger.error("unknown_scraper", source=source_name)
        return

    scraper = scraper_cls()
    result = await scraper.run()

    async with get_db_context() as db:
        svc = DealService(db)
        new_count, dup_count = await svc.save_scraped_deals(result)

        await svc.log_scrape_run(
            source=source_name,
            status="failed" if result.error else "success",
            deals_found=result.deals_found,
            deals_new=new_count,
            deals_duplicate=dup_count,
            started_at=result.started_at,
            finished_at=result.finished_at,
            error_message=result.error,
        )

    logger.info(
        "scrape_task_complete",
        source=source_name,
        new=new_count,
        duplicates=dup_count,
    )

    # Queue enrichment for new deals
    if new_count > 0:
        from app.workers.enrichment_tasks import enrich_pending_deals_task
        enrich_pending_deals_task.apply_async(countdown=5)
