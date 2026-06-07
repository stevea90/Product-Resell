"""
TrendService — orchestrates metric ingestion, trend computation, and anomaly detection.
All DB I/O lives here; the analyzer module stays pure.
"""
from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta, timezone
from typing import Optional

import httpx
import pandas as pd
from sqlalchemy import delete, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.models.trend import ProductMetric, ProductTrend, TrendAnomaly
from app.services.trend import analyzer
from app.services.trend.collectors import (
    amazon_collector,
    google_trends_collector,
    hotukdeals_collector,
    reddit_collector,
)

logger = get_logger(__name__)

# How many top-scored ASINs to hit Google Trends for (rate-limited)
GOOGLE_TRENDS_TOP_N = 15
REDDIT_BATCH_SIZE = 20


class TrendService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ── ASIN discovery ─────────────────────────────────────────────────────

    async def get_all_tracked_asins(self) -> list[tuple[str, Optional[str]]]:
        """Return (asin, title) tuples for all known products."""
        rows = (await self.db.execute(text("""
            SELECT DISTINCT ON (asin) asin, title
            FROM amazon_products
            WHERE asin IS NOT NULL
            ORDER BY asin, fetched_at DESC
        """))).fetchall()
        return [(r.asin, r.title) for r in rows]

    async def get_top_asins_by_score(self, n: int) -> list[tuple[str, Optional[str]]]:
        """Return the n highest-scored ASINs for rate-limited collectors."""
        rows = (await self.db.execute(text("""
            SELECT DISTINCT ON (ap.asin) ap.asin, ap.title
            FROM amazon_products ap
            JOIN opportunities o ON o.deal_id = ap.deal_id
            WHERE ap.asin IS NOT NULL
            ORDER BY ap.asin, o.score DESC NULLS LAST
            LIMIT :n
        """), {"n": n})).fetchall()
        return [(r.asin, r.title) for r in rows]

    # ── Metric ingestion ───────────────────────────────────────────────────

    async def ingest_all_metrics(self, target_date: Optional[date] = None) -> int:
        """
        Full daily ingestion:
          1. Amazon + HotUKDeals signals for every tracked ASIN
          2. Reddit mentions for top REDDIT_BATCH_SIZE ASINs
          3. Google Trends for top GOOGLE_TRENDS_TOP_N ASINs

        Returns total number of metric rows upserted.
        """
        if target_date is None:
            target_date = date.today()

        all_metrics: list[dict] = []

        # Cheap signals from existing DB data
        amazon_metrics = await amazon_collector.collect(self.db, target_date)
        hotuk_metrics = await hotukdeals_collector.collect(self.db, target_date)
        all_metrics.extend(amazon_metrics)
        all_metrics.extend(hotuk_metrics)

        # Reddit — batch, shared HTTP client
        top_asins = await self.get_top_asins_by_score(REDDIT_BATCH_SIZE)
        async with httpx.AsyncClient(timeout=15.0) as client:
            reddit_tasks = [
                reddit_collector.collect(asin, title, client, target_date)
                for asin, title in top_asins
            ]
            reddit_results = await asyncio.gather(*reddit_tasks, return_exceptions=True)
            for r in reddit_results:
                if isinstance(r, dict):
                    all_metrics.append(r)

        # Google Trends — sequential (rate-limited)
        gt_asins = await self.get_top_asins_by_score(GOOGLE_TRENDS_TOP_N)
        for asin, title in gt_asins:
            result = await google_trends_collector.collect(asin, title, target_date)
            if result:
                all_metrics.append(result)

        saved = await self._upsert_metrics(all_metrics)
        logger.info("metrics_ingested", date=str(target_date), total=saved)
        return saved

    async def _upsert_metrics(self, metrics: list[dict]) -> int:
        if not metrics:
            return 0
        count = 0
        for m in metrics:
            stmt = pg_insert(ProductMetric).values(
                asin=m["asin"],
                product_title=m.get("product_title"),
                date=m["date"],
                signal_type=m["signal_type"],
                value=m.get("value"),
                source=m["source"],
            ).on_conflict_do_update(
                constraint="uq_metric_asin_date_signal",
                set_={"value": m.get("value")},
            )
            await self.db.execute(stmt)
            count += 1
        await self.db.commit()
        return count

    # ── Trend computation ──────────────────────────────────────────────────

    async def compute_trend_for_asin(
        self, asin: str, product_title: Optional[str], target_date: Optional[date] = None
    ) -> Optional[ProductTrend]:
        if target_date is None:
            target_date = date.today()

        # Load last 30 days of metrics for this ASIN
        since = target_date - timedelta(days=30)
        rows = (await self.db.execute(
            select(ProductMetric)
            .where(ProductMetric.asin == asin)
            .where(ProductMetric.date >= since)
            .order_by(ProductMetric.date)
        )).scalars().all()

        if not rows:
            return None

        # Build per-signal series
        by_signal: dict[str, list[tuple[date, float]]] = {}
        for row in rows:
            if row.value is not None:
                by_signal.setdefault(row.signal_type, []).append((row.date, row.value))

        series_map: dict[str, pd.Series] = {}
        for sig, points in by_signal.items():
            idx, vals = zip(*points)
            series_map[sig] = pd.Series(list(vals), index=pd.to_datetime(list(idx)))

        # Compute signal scores using latest available value
        signal_scores: dict[str, Optional[float]] = {}
        raw_values: dict[str, Optional[float]] = {}

        for sig, series in series_map.items():
            if sig not in analyzer.SIGNAL_WEIGHTS:
                continue
            current = float(series.iloc[-1])
            raw_values[sig] = current
            signal_scores[sig] = analyzer.compute_signal_score(sig, current, series)

        demand_score = analyzer.compute_demand_score(signal_scores)
        signal_breakdown = analyzer.build_signal_breakdown(signal_scores, raw_values)

        # Use demand_score series for moving averages and z-score
        # Build a daily demand score series from available metrics
        demand_series = self._build_demand_series(rows)
        ma_7d, ma_30d = analyzer.compute_moving_averages(demand_series)
        z_score = analyzer.compute_z_score(demand_series)
        trend_direction = analyzer.classify_direction(ma_7d, ma_30d, z_score)

        # Upsert into product_trends
        stmt = pg_insert(ProductTrend).values(
            asin=asin,
            product_title=product_title,
            date=target_date,
            demand_score=round(demand_score, 2),
            trend_direction=trend_direction,
            ma_7d=round(ma_7d, 2) if ma_7d else None,
            ma_30d=round(ma_30d, 2) if ma_30d else None,
            z_score=round(z_score, 3) if z_score else None,
            signal_breakdown=signal_breakdown,
        ).on_conflict_do_update(
            constraint="uq_trend_asin_date",
            set_={
                "demand_score": round(demand_score, 2),
                "trend_direction": trend_direction,
                "ma_7d": round(ma_7d, 2) if ma_7d else None,
                "ma_30d": round(ma_30d, 2) if ma_30d else None,
                "z_score": round(z_score, 3) if z_score else None,
                "signal_breakdown": signal_breakdown,
                "computed_at": datetime.now(timezone.utc),
            },
        ).returning(ProductTrend)
        result = await self.db.execute(stmt)
        await self.db.commit()
        return result.scalar_one_or_none()

    def _build_demand_series(self, metrics: list[ProductMetric]) -> pd.Series:
        """Approximate a daily demand score series from raw metrics for MA/z-score."""
        by_date: dict[date, list[float]] = {}
        for m in metrics:
            if m.signal_type not in analyzer.SIGNAL_WEIGHTS or m.value is None:
                continue
            score = analyzer.compute_signal_score(m.signal_type, m.value, pd.Series([m.value]))
            by_date.setdefault(m.date, []).append(score * analyzer.SIGNAL_WEIGHTS[m.signal_type])

        if not by_date:
            return pd.Series(dtype=float)

        dates = sorted(by_date.keys())
        values = [sum(by_date[d]) for d in dates]
        return pd.Series(values, index=pd.to_datetime(dates))

    # ── Anomaly detection ──────────────────────────────────────────────────

    async def detect_anomalies_for_asin(
        self, asin: str, product_title: Optional[str]
    ) -> list[TrendAnomaly]:
        since = date.today() - timedelta(days=30)
        rows = (await self.db.execute(
            select(ProductMetric)
            .where(ProductMetric.asin == asin)
            .where(ProductMetric.date >= since)
            .order_by(ProductMetric.date)
        )).scalars().all()

        if not rows:
            return []

        by_signal: dict[str, pd.Series] = {}
        for sig in analyzer.SIGNAL_WEIGHTS:
            points = [(r.date, r.value) for r in rows if r.signal_type == sig and r.value is not None]
            if len(points) >= 7:
                idx, vals = zip(*points)
                by_signal[sig] = pd.Series(list(vals), index=pd.to_datetime(list(idx)))

        anomaly_dicts = analyzer.detect_anomalies(asin, by_signal, product_title)
        saved: list[TrendAnomaly] = []

        for a in anomaly_dicts:
            # Suppress duplicates within 24h
            cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
            existing = (await self.db.execute(
                select(TrendAnomaly.id)
                .where(TrendAnomaly.asin == asin)
                .where(TrendAnomaly.signal_type == a["signal_type"])
                .where(TrendAnomaly.detected_at >= cutoff)
            )).scalar_one_or_none()

            if existing:
                continue

            anomaly = TrendAnomaly(
                asin=a["asin"],
                product_title=a.get("product_title"),
                signal_type=a["signal_type"],
                z_score=a["z_score"],
                severity=a["severity"],
                description=a.get("description"),
                current_value=a.get("current_value"),
                baseline_value=a.get("baseline_value"),
            )
            self.db.add(anomaly)
            saved.append(anomaly)

        if saved:
            await self.db.commit()

        return saved

    # ── Query helpers ──────────────────────────────────────────────────────

    async def get_trend_history(self, asin: str, days: int = 30) -> list[ProductTrend]:
        since = date.today() - timedelta(days=days)
        result = await self.db.execute(
            select(ProductTrend)
            .where(ProductTrend.asin == asin)
            .where(ProductTrend.date >= since)
            .order_by(ProductTrend.date)
        )
        return list(result.scalars().all())

    async def get_raw_metrics(self, asin: str, days: int = 30) -> list[ProductMetric]:
        since = date.today() - timedelta(days=days)
        result = await self.db.execute(
            select(ProductMetric)
            .where(ProductMetric.asin == asin)
            .where(ProductMetric.date >= since)
            .order_by(ProductMetric.date, ProductMetric.signal_type)
        )
        return list(result.scalars().all())

    async def get_recent_anomalies(
        self, severity: Optional[str] = None, limit: int = 20
    ) -> tuple[list[TrendAnomaly], int]:
        stmt = select(TrendAnomaly).order_by(TrendAnomaly.detected_at.desc())
        count_stmt = select(TrendAnomaly)
        if severity:
            stmt = stmt.where(TrendAnomaly.severity == severity)
            count_stmt = count_stmt.where(TrendAnomaly.severity == severity)

        from sqlalchemy import func
        total = (await self.db.execute(
            select(func.count()).select_from(count_stmt.subquery())
        )).scalar_one()

        result = await self.db.execute(stmt.limit(limit))
        return list(result.scalars().all()), total

    async def get_trending_products(self, limit: int = 20) -> list[ProductTrend]:
        today = date.today()
        result = await self.db.execute(
            select(ProductTrend)
            .where(ProductTrend.date >= today - timedelta(days=2))
            .where(ProductTrend.trend_direction.in_(["rising", "spiking"]))
            .order_by(ProductTrend.demand_score.desc().nullslast())
            .limit(limit)
        )
        return list(result.scalars().all())
