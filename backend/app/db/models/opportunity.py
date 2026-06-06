"""
An Opportunity is the fully-analysed resale case for a deal:
profitability numbers + opportunity score + AI narrative.
This is what the dashboard displays.
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class Opportunity(Base):
    __tablename__ = "opportunities"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    deal_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("deals.id", ondelete="CASCADE"), unique=True, index=True
    )

    # ── Profitability ─────────────────────────────────────────
    buy_price: Mapped[Optional[float]] = mapped_column(Float)   # deal price incl. VAT
    sell_price: Mapped[Optional[float]] = mapped_column(Float)  # expected Amazon sell price
    gross_profit: Mapped[Optional[float]] = mapped_column(Float)
    net_profit: Mapped[Optional[float]] = mapped_column(Float)
    roi_percent: Mapped[Optional[float]] = mapped_column(Float)
    margin_percent: Mapped[Optional[float]] = mapped_column(Float)
    break_even_price: Mapped[Optional[float]] = mapped_column(Float)
    estimated_payout: Mapped[Optional[float]] = mapped_column(Float)  # after all fees

    # ── Fee breakdown ─────────────────────────────────────────
    amazon_referral_fee: Mapped[Optional[float]] = mapped_column(Float)
    fba_fee: Mapped[Optional[float]] = mapped_column(Float)
    vat_amount: Mapped[Optional[float]] = mapped_column(Float)
    shipping_cost: Mapped[Optional[float]] = mapped_column(Float)
    total_costs: Mapped[Optional[float]] = mapped_column(Float)

    # ── Opportunity score (0–100) ─────────────────────────────
    score: Mapped[Optional[int]] = mapped_column(Integer, index=True)
    confidence_level: Mapped[Optional[str]] = mapped_column(
        String(20)  # "low" | "medium" | "high" | "very_high"
    )

    # ── Score component breakdown ─────────────────────────────
    score_roi: Mapped[Optional[float]] = mapped_column(Float)
    score_demand: Mapped[Optional[float]] = mapped_column(Float)
    score_competition: Mapped[Optional[float]] = mapped_column(Float)
    score_reviews: Mapped[Optional[float]] = mapped_column(Float)
    score_price_stability: Mapped[Optional[float]] = mapped_column(Float)
    score_community: Mapped[Optional[float]] = mapped_column(Float)

    # ── AI narrative ──────────────────────────────────────────
    score_reasoning: Mapped[Optional[str]] = mapped_column(Text)
    tags: Mapped[Optional[str]] = mapped_column(String(512))  # comma-separated

    # ── Alert state ───────────────────────────────────────────
    alert_sent: Mapped[bool] = mapped_column(default=False)
    alert_sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # ── Timestamps ────────────────────────────────────────────
    scored_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # ── Relationships ─────────────────────────────────────────
    deal: Mapped["Deal"] = relationship(back_populates="opportunity")  # noqa: F821

    def __repr__(self) -> str:
        return f"<Opportunity deal_id={self.deal_id} score={self.score} roi={self.roi_percent:.1f}%>"
