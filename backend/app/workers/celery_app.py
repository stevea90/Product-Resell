"""
Celery application setup with beat schedule.

Queues:
  scraping    — deal fetching from source retailers
  enrichment  — Amazon product data lookups
  scoring     — profitability calculation + opportunity scoring

Beat schedule (periodic tasks):
  scrape_hotukdeals_task  — every 30 minutes
  enrich_pending_deals    — every 10 minutes
"""
from celery import Celery
from celery.schedules import crontab

from app.core.config import settings

celery_app = Celery(
    "arbitrageai",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=[
        "app.workers.scraping_tasks",
        "app.workers.enrichment_tasks",
        "app.workers.scoring_tasks",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Europe/London",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,  # Don't prefetch — ensure fair distribution
    task_routes={
        "app.workers.scraping_tasks.*": {"queue": "scraping"},
        "app.workers.enrichment_tasks.*": {"queue": "enrichment"},
        "app.workers.scoring_tasks.*": {"queue": "scoring"},
    },
    beat_schedule={
        "scrape-all-sources": {
            "task": "app.workers.scraping_tasks.scrape_all_task",
            "schedule": 1800,  # Every 30 minutes
            "options": {"queue": "scraping"},
        },
        "enrich-pending-deals": {
            "task": "app.workers.enrichment_tasks.enrich_pending_deals_task",
            "schedule": 600,  # Every 10 minutes
            "options": {"queue": "enrichment"},
        },
    },
)
