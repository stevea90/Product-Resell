"""
Demand trend Celery tasks.

  ingest_daily_metrics_task  — runs at 2am, ingests all signals for all ASINs
  compute_daily_trends_task  — runs at 3am, computes demand scores from metrics
  detect_anomalies_task      — runs every hour, detects z-score spikes
"""
import asyncio

from app.core.logging import get_logger
from app.db.database import get_db_context
from app.services.trend.trend_service import TrendService
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
    name="app.workers.trend_tasks.ingest_daily_metrics_task",
    bind=True,
    max_retries=2,
    soft_time_limit=3600,
)
def ingest_daily_metrics_task(self):
    """Daily metric ingestion — all ASINs, all signals."""
    logger.info("trend_ingest_started", task_id=self.request.id)
    try:
        _run_async(_ingest_metrics())
    except Exception as exc:
        logger.error("trend_ingest_failed", error=str(exc))
        raise self.retry(exc=exc)


@celery_app.task(
    name="app.workers.trend_tasks.compute_daily_trends_task",
    bind=True,
    max_retries=2,
    soft_time_limit=1800,
)
def compute_daily_trends_task(self):
    """Compute demand scores and MAs from today's ingested metrics."""
    logger.info("trend_compute_started", task_id=self.request.id)
    try:
        _run_async(_compute_trends())
    except Exception as exc:
        logger.error("trend_compute_failed", error=str(exc))
        raise self.retry(exc=exc)


@celery_app.task(
    name="app.workers.trend_tasks.detect_anomalies_task",
    bind=True,
    max_retries=1,
    soft_time_limit=600,
)
def detect_anomalies_task(self):
    """Hourly anomaly detection — z-score analysis across all tracked ASINs."""
    logger.info("trend_anomaly_detect_started", task_id=self.request.id)
    try:
        _run_async(_detect_anomalies())
    except Exception as exc:
        logger.error("trend_anomaly_detect_failed", error=str(exc))
        raise self.retry(exc=exc)


async def _ingest_metrics() -> None:
    async with get_db_context() as db:
        svc = TrendService(db)
        total = await svc.ingest_all_metrics()
        logger.info("trend_ingest_complete", metrics_saved=total)
    # Trigger trend computation shortly after ingestion
    compute_daily_trends_task.apply_async(countdown=120, queue="enrichment")


async def _compute_trends() -> None:
    async with get_db_context() as db:
        svc = TrendService(db)
        asins = await svc.get_all_tracked_asins()

    computed = 0
    errors = 0
    for asin, title in asins:
        try:
            async with get_db_context() as db:
                svc = TrendService(db)
                trend = await svc.compute_trend_for_asin(asin, title)
                if trend:
                    computed += 1
        except Exception as exc:
            logger.warning("trend_compute_error", asin=asin, error=str(exc))
            errors += 1

    logger.info("trend_compute_complete", computed=computed, errors=errors)


async def _detect_anomalies() -> None:
    async with get_db_context() as db:
        svc = TrendService(db)
        asins = await svc.get_all_tracked_asins()

    total_anomalies = 0
    for asin, title in asins:
        try:
            async with get_db_context() as db:
                svc = TrendService(db)
                found = await svc.detect_anomalies_for_asin(asin, title)
                total_anomalies += len(found)
        except Exception as exc:
            logger.warning("anomaly_detect_error", asin=asin, error=str(exc))

    logger.info("anomaly_detection_complete", anomalies_saved=total_anomalies)
