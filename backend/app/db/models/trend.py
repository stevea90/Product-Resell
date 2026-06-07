"""
Demand trend detection models.

product_metrics  — raw time-series signal values per ASIN per day
product_trends   — computed demand score + MA + z-score per ASIN per day
trend_anomalies  — statistically significant spikes detected by z-score
"""
from datetime import date as date_type, datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Float,
    JSON,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class ProductMetric(Base):
    """One row = one signal value for one ASIN on one day."""
    __tablename__ = "product_metrics"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    asin: Mapped[str] = mapped_column(String(20), index=True)
    product_title: Mapped[Optional[str]] = mapped_column(String(500))
    date: Mapped[date_type] = mapped_column(Date, index=True)
    # sales_rank | review_count | review_velocity | fba_seller_count |
    # hot_score  | comment_count | reddit_mentions | google_trends
    signal_type: Mapped[str] = mapped_column(String(50))
    value: Mapped[Optional[float]] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(50))  # keepa | hotukdeals | reddit | google

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint("asin", "date", "signal_type", name="uq_metric_asin_date_signal"),
    )


class ProductTrend(Base):
    """Computed aggregate per ASIN per day — demand score, MAs, z-score."""
    __tablename__ = "product_trends"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    asin: Mapped[str] = mapped_column(String(20), index=True)
    product_title: Mapped[Optional[str]] = mapped_column(String(500))
    date: Mapped[date_type] = mapped_column(Date, index=True)

    demand_score: Mapped[Optional[float]] = mapped_column(Float)  # 0-100
    # rising | falling | stable | spiking
    trend_direction: Mapped[Optional[str]] = mapped_column(String(20))

    ma_7d: Mapped[Optional[float]] = mapped_column(Float)
    ma_30d: Mapped[Optional[float]] = mapped_column(Float)
    z_score: Mapped[Optional[float]] = mapped_column(Float)

    # Per-signal normalised scores that fed into demand_score
    signal_breakdown: Mapped[Optional[dict]] = mapped_column(JSON)

    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint("asin", "date", name="uq_trend_asin_date"),
    )


class TrendAnomaly(Base):
    """A statistically significant spike (|z| > 2.0) for a signal."""
    __tablename__ = "trend_anomalies"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    asin: Mapped[str] = mapped_column(String(20), index=True)
    product_title: Mapped[Optional[str]] = mapped_column(String(500))

    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    signal_type: Mapped[str] = mapped_column(String(50))
    z_score: Mapped[Optional[float]] = mapped_column(Float)
    severity: Mapped[str] = mapped_column(String(20))  # low | medium | high | critical

    description: Mapped[Optional[str]] = mapped_column(Text)
    current_value: Mapped[Optional[float]] = mapped_column(Float)
    baseline_value: Mapped[Optional[float]] = mapped_column(Float)

    is_acknowledged: Mapped[bool] = mapped_column(Boolean, default=False)
