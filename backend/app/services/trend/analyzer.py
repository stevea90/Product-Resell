"""
Demand trend analytics engine — pure computation, no DB I/O.

Accepts pandas DataFrames of historical metrics and produces:
  - moving averages (7d, 30d)
  - z-score (30d rolling window)
  - per-signal normalised scores (0-100)
  - weighted demand score (0-100)
  - trend direction
  - anomaly detections
"""
from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

# Signal weights must sum to 1.0
SIGNAL_WEIGHTS: dict[str, float] = {
    "sales_rank": 0.35,
    "review_count": 0.20,
    "fba_seller_count": 0.15,
    "hot_score": 0.15,
    "reddit_mentions": 0.10,
    "google_trends": 0.05,
}

# |z| threshold → severity label
ANOMALY_THRESHOLDS = [
    (4.0, "critical"),
    (3.0, "high"),
    (2.5, "medium"),
    (2.0, "low"),
]

# Caps used for sales_rank normalisation (lower rank = higher demand)
SALES_RANK_CAP = 500_000


def _normalise_sales_rank(value: float) -> float:
    """Convert BSR to a 0-100 demand score (higher = more demand)."""
    if value <= 0:
        return 100.0
    score = max(0.0, (1 - value / SALES_RANK_CAP) * 100)
    return min(100.0, score)


def _normalise_percentile(value: float, series: pd.Series) -> float:
    """Score a value as its percentile within the historical series (0-100)."""
    if series.empty or series.std() == 0:
        return 50.0
    rank = (series <= value).sum() / len(series) * 100
    return float(np.clip(rank, 0, 100))


def compute_moving_averages(series: pd.Series) -> tuple[Optional[float], Optional[float]]:
    """Return (ma_7d, ma_30d). Returns None when insufficient history."""
    ma_7d = None
    ma_30d = None
    if len(series) >= 3:
        ma_7d = float(series.rolling(window=7, min_periods=3).mean().iloc[-1])
    if len(series) >= 7:
        ma_30d = float(series.rolling(window=30, min_periods=7).mean().iloc[-1])
    return ma_7d, ma_30d


def compute_z_score(series: pd.Series, window: int = 30) -> Optional[float]:
    """30-day rolling z-score for the most recent value. None if insufficient data."""
    if len(series) < 7:
        return None
    rolling_mean = series.rolling(window=window, min_periods=7).mean().iloc[-1]
    rolling_std = series.rolling(window=window, min_periods=7).std().iloc[-1]
    if pd.isna(rolling_std) or rolling_std == 0:
        return None
    return float((series.iloc[-1] - rolling_mean) / rolling_std)


def compute_signal_score(signal_type: str, current_value: float, history: pd.Series) -> float:
    """Normalise a single signal to 0-100."""
    if signal_type == "sales_rank":
        return _normalise_sales_rank(current_value)
    if signal_type == "fba_seller_count":
        # Moderate competition (3-8 sellers) is ideal for FBA entry
        ideal = 5.0
        diff = abs(current_value - ideal)
        return float(np.clip(100 - diff * 10, 0, 100))
    return _normalise_percentile(current_value, history)


def compute_demand_score(signal_scores: dict[str, Optional[float]]) -> float:
    """
    Weighted average of available signal scores.
    Missing signals redistribute their weight proportionally.
    """
    available = {k: v for k, v in signal_scores.items() if v is not None}
    if not available:
        return 50.0

    total_weight = sum(SIGNAL_WEIGHTS.get(k, 0) for k in available)
    if total_weight == 0:
        return 50.0

    weighted_sum = sum(
        v * SIGNAL_WEIGHTS.get(k, 0) for k, v in available.items()
    )
    return float(np.clip(weighted_sum / total_weight, 0, 100))


def classify_direction(
    ma_7d: Optional[float],
    ma_30d: Optional[float],
    z_score: Optional[float],
) -> str:
    if z_score is not None and abs(z_score) >= 3.0:
        return "spiking"
    if ma_7d is not None and ma_30d is not None and ma_30d > 0:
        ratio = ma_7d / ma_30d
        if ratio > 1.10:
            return "rising"
        if ratio < 0.90:
            return "falling"
    return "stable"


def severity_for_z(z: float) -> Optional[str]:
    for threshold, label in ANOMALY_THRESHOLDS:
        if abs(z) >= threshold:
            return label
    return None


def detect_anomalies(
    asin: str,
    metrics_by_signal: dict[str, pd.Series],
    product_title: Optional[str] = None,
) -> list[dict]:
    """
    Return a list of anomaly dicts for signals whose latest z-score crosses a threshold.
    """
    anomalies = []
    for signal_type, series in metrics_by_signal.items():
        if series.empty:
            continue
        z = compute_z_score(series)
        if z is None:
            continue
        severity = severity_for_z(z)
        if severity is None:
            continue

        baseline = float(series.rolling(30, min_periods=7).mean().iloc[-1])
        current = float(series.iloc[-1])
        direction = "above" if z > 0 else "below"

        anomalies.append({
            "asin": asin,
            "product_title": product_title,
            "signal_type": signal_type,
            "z_score": round(z, 3),
            "severity": severity,
            "current_value": current,
            "baseline_value": round(baseline, 3),
            "description": (
                f"{signal_type.replace('_', ' ').title()} is {abs(z):.1f}σ "
                f"{direction} its 30-day baseline "
                f"({current:.0f} vs {baseline:.0f})."
            ),
        })
    return anomalies


def build_signal_breakdown(
    signal_scores: dict[str, Optional[float]],
    raw_values: dict[str, Optional[float]],
) -> dict:
    breakdown = {}
    for sig, score in signal_scores.items():
        weight = SIGNAL_WEIGHTS.get(sig, 0)
        breakdown[sig] = {
            "raw": raw_values.get(sig),
            "normalised": round(score, 1) if score is not None else None,
            "weighted": round(score * weight, 2) if score is not None else None,
        }
    return breakdown
