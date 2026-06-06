"""
Deals API endpoints.
Provides the dashboard with filtered, sorted, paginated opportunity data.
"""
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.database import get_db
from app.db.models.deal import Deal, DealStatus
from app.db.models.opportunity import Opportunity
from app.db.models.product import AmazonProduct
from app.schemas.deal import DealListResponse, DealResponse, OpportunitySchema, AmazonProductSchema, StatsResponse

router = APIRouter(prefix="/deals", tags=["deals"])


@router.get("", response_model=DealListResponse)
async def list_deals(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    category: Optional[str] = Query(None),
    min_score: Optional[int] = Query(None, ge=0, le=100),
    min_roi: Optional[float] = Query(None),
    source: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    sort_by: str = Query("score", enum=["score", "roi", "profit", "date", "hot_score"]),
    db: AsyncSession = Depends(get_db),
):
    """
    List deals with opportunities.
    Only returns SCORED deals by default (enriched + profitability calculated).
    """
    stmt = (
        select(Deal)
        .options(
            selectinload(Deal.opportunity),
        )
        .join(Opportunity, Deal.id == Opportunity.deal_id)
        .where(Deal.status == DealStatus.SCORED)
    )

    if category:
        stmt = stmt.where(Deal.category == category)
    if source:
        stmt = stmt.where(Deal.source == source)
    if search:
        stmt = stmt.where(Deal.title.ilike(f"%{search}%"))
    if min_score is not None:
        stmt = stmt.where(Opportunity.score >= min_score)
    if min_roi is not None:
        stmt = stmt.where(Opportunity.roi_percent >= min_roi)

    # Count total
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar_one()

    # Apply sort
    sort_map = {
        "score": Opportunity.score.desc(),
        "roi": Opportunity.roi_percent.desc(),
        "profit": Opportunity.net_profit.desc(),
        "date": Deal.first_seen_at.desc(),
        "hot_score": Deal.hot_score.desc().nullslast(),
    }
    stmt = stmt.order_by(sort_map[sort_by])
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(stmt)
    deals = result.scalars().all()

    # Load Amazon products separately to avoid N+1
    deal_ids = [d.id for d in deals]
    amazon_map = {}
    if deal_ids:
        amazon_result = await db.execute(
            select(AmazonProduct).where(AmazonProduct.deal_id.in_(deal_ids))
        )
        for ap in amazon_result.scalars():
            amazon_map[ap.deal_id] = ap

    items = []
    for deal in deals:
        opp_schema = None
        if deal.opportunity:
            opp_schema = OpportunitySchema.from_orm_with_tags(deal.opportunity)

        amazon_schema = None
        if deal.id in amazon_map:
            amazon_schema = AmazonProductSchema.model_validate(amazon_map[deal.id])

        items.append(DealResponse(
            id=deal.id,
            source=deal.source.value,
            title=deal.title,
            deal_price=deal.deal_price,
            original_price=deal.original_price,
            discount_percent=deal.discount_percent,
            currency=deal.currency,
            category=deal.category.value if deal.category else None,
            image_url=deal.image_url,
            source_url=deal.source_url,
            product_url=deal.product_url,
            retailer=deal.retailer,
            hot_score=deal.hot_score,
            comment_count=deal.comment_count,
            status=deal.status.value,
            first_seen_at=deal.first_seen_at,
            opportunity=opp_schema,
            amazon_product=amazon_schema,
        ))

    return DealListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        pages=max(1, (total + page_size - 1) // page_size),
    )


@router.get("/stats", response_model=StatsResponse)
async def get_stats(db: AsyncSession = Depends(get_db)):
    """Dashboard statistics summary."""
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

    total_deals = (await db.execute(select(func.count(Deal.id)))).scalar_one()
    scored_deals = (
        await db.execute(
            select(func.count(Deal.id)).where(Deal.status == DealStatus.SCORED)
        )
    ).scalar_one()

    high_conf = (
        await db.execute(
            select(func.count(Opportunity.id)).where(Opportunity.score >= 75)
        )
    ).scalar_one()

    avg_roi = (
        await db.execute(
            select(func.avg(Opportunity.roi_percent)).where(
                Opportunity.roi_percent.isnot(None)
            )
        )
    ).scalar_one()

    deals_today = (
        await db.execute(
            select(func.count(Deal.id)).where(Deal.first_seen_at >= today)
        )
    ).scalar_one()

    # Category breakdown
    cat_result = await db.execute(
        select(Deal.category, func.count(Deal.id))
        .where(Deal.status == DealStatus.SCORED)
        .group_by(Deal.category)
    )
    top_categories = {
        str(row[0].value if row[0] else "other"): row[1]
        for row in cat_result.fetchall()
    }

    return StatsResponse(
        total_deals=total_deals,
        scored_deals=scored_deals,
        high_confidence_opportunities=high_conf,
        avg_roi_percent=round(avg_roi, 1) if avg_roi else None,
        top_categories=top_categories,
        deals_today=deals_today,
    )


@router.post("/scrape", status_code=202)
async def trigger_scrape(source: str = "hotukdeals"):
    """Manually trigger a scrape run. Returns immediately (async task)."""
    from app.workers.scraping_tasks import scrape_hotukdeals_task
    task = scrape_hotukdeals_task.apply_async()
    return {"task_id": task.id, "status": "queued", "source": source}
