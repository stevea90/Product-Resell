"""
Extracts HotUKDeals community signals from the deals table.

For each ASIN that has an associated deal on a given day, computes:
  hot_score     — max temperature seen for that ASIN today
  comment_count — max comment count seen for that ASIN today

Joins deals → amazon_products to resolve ASIN.
"""
from datetime import date, timedelta
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger

logger = get_logger(__name__)


async def collect(db: AsyncSession, target_date: Optional[date] = None) -> list[dict]:
    if target_date is None:
        target_date = date.today()

    start = target_date
    end = target_date + timedelta(days=1)

    stmt = text("""
        SELECT
            ap.asin,
            ap.title          AS product_title,
            MAX(d.hot_score)  AS hot_score,
            MAX(d.comment_count) AS comment_count
        FROM deals d
        JOIN amazon_products ap ON ap.deal_id = d.id
        WHERE d.first_seen_at >= :start
          AND d.first_seen_at  < :end
          AND ap.asin IS NOT NULL
        GROUP BY ap.asin, ap.title
    """)
    rows = (await db.execute(stmt, {"start": start, "end": end})).fetchall()

    metrics: list[dict] = []
    for row in rows:
        base = {
            "asin": row.asin,
            "product_title": row.product_title,
            "date": target_date,
            "source": "hotukdeals",
        }
        if row.hot_score is not None:
            metrics.append({**base, "signal_type": "hot_score", "value": float(row.hot_score)})
        if row.comment_count is not None:
            metrics.append({**base, "signal_type": "comment_count", "value": float(row.comment_count)})

    logger.info("hotukdeals_metrics_collected", count=len(metrics), date=str(target_date))
    return metrics
