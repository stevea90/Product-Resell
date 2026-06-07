"""Pydantic response schemas for the demand trend API."""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel


class SignalBreakdownItem(BaseModel):
    raw: Optional[float] = None
    normalised: Optional[float] = None
    weighted: Optional[float] = None


class TrendHistoryPoint(BaseModel):
    date: date
    demand_score: float
    trend_direction: str
    ma_7d: Optional[float] = None
    ma_30d: Optional[float] = None
    z_score: Optional[float] = None
    signal_breakdown: Optional[dict[str, SignalBreakdownItem]] = None

    model_config = {"from_attributes": True}


class TrendHistoryResponse(BaseModel):
    asin: str
    product_title: Optional[str] = None
    days: int
    history: list[TrendHistoryPoint]


class AnomalyItem(BaseModel):
    id: int
    asin: str
    product_title: Optional[str] = None
    detected_at: datetime
    signal_type: str
    z_score: float
    severity: str
    description: Optional[str] = None
    current_value: Optional[float] = None
    baseline_value: Optional[float] = None
    is_acknowledged: bool

    model_config = {"from_attributes": True}


class AnomalyFeedResponse(BaseModel):
    total: int
    anomalies: list[AnomalyItem]


class TrendingProduct(BaseModel):
    asin: str
    product_title: Optional[str] = None
    date: date
    demand_score: float
    trend_direction: str
    ma_7d: Optional[float] = None
    ma_30d: Optional[float] = None
    z_score: Optional[float] = None

    model_config = {"from_attributes": True}


class TrendingProductsResponse(BaseModel):
    count: int
    products: list[TrendingProduct]
