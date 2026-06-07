"""
Demand trend API endpoints.

GET /api/v1/trends/{asin}/history   — 30-day trend chart data
GET /api/v1/trends/anomalies        — anomaly alert feed
GET /api/v1/trends/trending         — currently rising/spiking products
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.schemas.trend import (
    AnomalyFeedResponse,
    AnomalyItem,
    TrendHistoryPoint,
    TrendHistoryResponse,
    TrendingProduct,
    TrendingProductsResponse,
)
from app.services.trend.trend_service import TrendService

router = APIRouter(prefix="/trends", tags=["trends"])


@router.get("/trending", response_model=TrendingProductsResponse)
async def get_trending_products(
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """Products with rising or spiking demand in the last 48 hours."""
    svc = TrendService(db)
    products = await svc.get_trending_products(limit=limit)
    return TrendingProductsResponse(
        count=len(products),
        products=[TrendingProduct.model_validate(p) for p in products],
    )


@router.get("/anomalies", response_model=AnomalyFeedResponse)
async def get_anomalies(
    severity: Optional[str] = Query(None, pattern="^(low|medium|high|critical)$"),
    limit: int = Query(20, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    """Recent anomaly alerts, optionally filtered by severity."""
    svc = TrendService(db)
    anomalies, total = await svc.get_recent_anomalies(severity=severity, limit=limit)
    return AnomalyFeedResponse(
        total=total,
        anomalies=[AnomalyItem.model_validate(a) for a in anomalies],
    )


@router.get("/{asin}/history", response_model=TrendHistoryResponse)
async def get_trend_history(
    asin: str,
    days: int = Query(30, ge=7, le=90),
    db: AsyncSession = Depends(get_db),
):
    """Historical demand trend data for a single ASIN."""
    svc = TrendService(db)
    history = await svc.get_trend_history(asin=asin, days=days)
    if not history:
        raise HTTPException(status_code=404, detail="No trend data found for this ASIN")

    product_title = history[-1].product_title if history else None
    points = [TrendHistoryPoint.model_validate(h) for h in history]
    return TrendHistoryResponse(
        asin=asin,
        product_title=product_title,
        days=days,
        history=points,
    )
