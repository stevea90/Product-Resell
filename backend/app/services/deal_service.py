"""
Deal persistence service.
Handles upsert logic, duplicate detection, and status transitions.
"""
from datetime import datetime
from typing import List, Optional, Tuple

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.models.deal import Deal, DealSource, DealStatus
from app.db.models.scrape_run import ScrapeRun
from app.services.scrapers.base import ScrapedDeal, ScrapeResult

logger = get_logger(__name__)


class DealService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def save_scraped_deals(
        self, result: ScrapeResult
    ) -> Tuple[int, int]:
        """
        Persist scraped deals. Returns (new_count, duplicate_count).
        Uses INSERT ... ON CONFLICT DO NOTHING to atomically handle duplicates.
        """
        new_count = 0
        duplicate_count = 0

        for deal_data in result.deals:
            try:
                stmt = (
                    insert(Deal)
                    .values(
                        source=DealSource(deal_data.source),
                        source_id=deal_data.source_id,
                        source_url=deal_data.source_url,
                        title=deal_data.title,
                        description=deal_data.description,
                        retailer=deal_data.retailer,
                        product_url=deal_data.product_url,
                        image_url=deal_data.image_url,
                        category=deal_data.category,
                        deal_price=deal_data.deal_price,
                        original_price=deal_data.original_price,
                        discount_percent=deal_data.discount_percent,
                        currency=deal_data.currency,
                        hot_score=deal_data.hot_score,
                        comment_count=deal_data.comment_count,
                        deal_posted_at=deal_data.deal_posted_at,
                        status=DealStatus.PENDING,
                    )
                    .on_conflict_do_nothing(constraint="uq_deals_source_url")
                    .returning(Deal.id)
                )

                result_proxy = await self.db.execute(stmt)
                row = result_proxy.fetchone()

                if row:
                    new_count += 1
                    logger.debug("deal_saved", deal_id=row[0], title=deal_data.title[:50])
                else:
                    duplicate_count += 1

            except Exception as exc:
                logger.error("deal_save_error", title=deal_data.title, error=str(exc))

        await self.db.commit()
        return new_count, duplicate_count

    async def log_scrape_run(
        self,
        source: str,
        status: str,
        deals_found: int,
        deals_new: int,
        deals_duplicate: int,
        started_at: datetime,
        finished_at: Optional[datetime] = None,
        error_message: Optional[str] = None,
    ) -> ScrapeRun:
        run = ScrapeRun(
            source=source,
            status=status,
            deals_found=deals_found,
            deals_new=deals_new,
            deals_duplicate=deals_duplicate,
            error_message=error_message,
            started_at=started_at,
            finished_at=finished_at,
            duration_seconds=(finished_at - started_at).total_seconds() if finished_at else None,
        )
        self.db.add(run)
        await self.db.commit()
        return run

    async def get_pending_deals(self, limit: int = 50) -> List[Deal]:
        """Get deals awaiting Amazon enrichment."""
        stmt = (
            select(Deal)
            .where(Deal.status == DealStatus.PENDING)
            .order_by(Deal.hot_score.desc().nullslast(), Deal.first_seen_at.desc())
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def mark_deal_enriching(self, deal_id: int) -> None:
        await self.db.execute(
            update(Deal).where(Deal.id == deal_id).values(status=DealStatus.ENRICHING)
        )
        await self.db.commit()

    async def mark_deal_scored(self, deal_id: int) -> None:
        await self.db.execute(
            update(Deal).where(Deal.id == deal_id).values(status=DealStatus.SCORED)
        )
        await self.db.commit()

    async def mark_deal_ignored(self, deal_id: int) -> None:
        await self.db.execute(
            update(Deal).where(Deal.id == deal_id).values(status=DealStatus.IGNORED)
        )
        await self.db.commit()

    async def get_deals_for_dashboard(
        self,
        page: int = 1,
        page_size: int = 20,
        category: Optional[str] = None,
        min_score: Optional[int] = None,
        min_roi: Optional[float] = None,
        source: Optional[str] = None,
        search: Optional[str] = None,
    ) -> Tuple[List[Deal], int]:
        """Paginated deals for dashboard with filters."""
        from sqlalchemy import func, or_

        stmt = select(Deal).where(Deal.status == DealStatus.SCORED)

        if category:
            stmt = stmt.where(Deal.category == category)
        if source:
            stmt = stmt.where(Deal.source == source)
        if search:
            stmt = stmt.where(Deal.title.ilike(f"%{search}%"))

        # Count total
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await self.db.execute(count_stmt)).scalar_one()

        # Apply ordering and pagination
        stmt = (
            stmt.order_by(Deal.first_seen_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )

        result = await self.db.execute(stmt)
        return list(result.scalars().all()), total
