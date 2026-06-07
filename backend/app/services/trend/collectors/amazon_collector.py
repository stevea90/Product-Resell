"""
Extracts Amazon demand signals from existing amazon_products table.

Signals produced (one row per ASIN per run):
  sales_rank       — BSR at time of last Keepa fetch
  review_count     — total review count
  review_velocity  — daily review growth vs previous reading
  fba_seller_count — number of FBA sellers competing

No external API calls needed — all data already in the database.
"""
from datetime import date, timedelta
from typing import Optional

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.models.product import AmazonProduct

logger = get_logger(__name__)


async def collect(db: AsyncSession, target_date: Optional[date] = None) -> list[dict]:
    """
    Return a list of metric dicts for upsert into product_metrics.
    Each dict: {asin, product_title, date, signal_type, value, source}
    """
    if target_date is None:
        target_date = date.today()

    # Fetch latest amazon_products record per ASIN
    stmt = text("""
        SELECT DISTINCT ON (asin)
            asin,
            title AS product_title,
            sales_rank,
            review_count,
            fba_seller_count,
            fetched_at
        FROM amazon_products
        WHERE asin IS NOT NULL
        ORDER BY asin, fetched_at DESC
    """)
    rows = (await db.execute(stmt)).fetchall()

    # Fetch previous review_count for velocity calculation
    prev_stmt = text("""
        SELECT asin, value
        FROM product_metrics
        WHERE signal_type = 'review_count'
          AND date = :prev_date
    """)
    prev_rows = (await db.execute(prev_stmt, {"prev_date": target_date - timedelta(days=1)})).fetchall()
    prev_review = {r.asin: r.value for r in prev_rows}

    metrics: list[dict] = []
    for row in rows:
        base = {
            "asin": row.asin,
            "product_title": row.product_title,
            "date": target_date,
            "source": "keepa",
        }

        if row.sales_rank is not None:
            metrics.append({**base, "signal_type": "sales_rank", "value": float(row.sales_rank)})

        if row.review_count is not None:
            metrics.append({**base, "signal_type": "review_count", "value": float(row.review_count)})
            # velocity = new reviews since yesterday
            prev = prev_review.get(row.asin)
            if prev is not None:
                velocity = max(0.0, float(row.review_count) - prev)
                metrics.append({**base, "signal_type": "review_velocity", "value": velocity})

        if row.fba_seller_count is not None:
            metrics.append({**base, "signal_type": "fba_seller_count", "value": float(row.fba_seller_count)})

    logger.info("amazon_metrics_collected", count=len(metrics), asins=len(rows))
    return metrics
