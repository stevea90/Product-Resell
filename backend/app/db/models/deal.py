"""
A Deal is a product listing discovered from a source retailer (HotUKDeals, Argos, etc.)
before we know anything about its resale potential.
"""
import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    Float,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class DealSource(str, enum.Enum):
    HOTUKDEALS = "hotukdeals"
    SMYTHS = "smyths"
    ARGOS = "argos"
    CURRYS = "currys"
    MANUAL = "manual"


class DealCategory(str, enum.Enum):
    TOYS = "toys"
    LEGO = "lego"
    GAMING = "gaming"
    ELECTRONICS = "electronics"
    OTHER = "other"


class DealStatus(str, enum.Enum):
    PENDING = "pending"          # Scraped, not yet enriched
    ENRICHING = "enriching"      # Amazon lookup in progress
    SCORED = "scored"            # Full analysis complete
    IGNORED = "ignored"          # Below threshold, filtered out
    EXPIRED = "expired"          # Deal no longer active


class Deal(Base):
    __tablename__ = "deals"
    __table_args__ = (
        # Prevent re-inserting the same deal URL multiple times
        UniqueConstraint("source_url", name="uq_deals_source_url"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    # ── Source metadata ───────────────────────────────────────
    source: Mapped[DealSource] = mapped_column(Enum(DealSource), nullable=False, index=True)
    source_id: Mapped[Optional[str]] = mapped_column(String(255), index=True)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)

    # ── Product info ──────────────────────────────────────────
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    retailer: Mapped[Optional[str]] = mapped_column(String(255))
    product_url: Mapped[Optional[str]] = mapped_column(Text)
    image_url: Mapped[Optional[str]] = mapped_column(Text)
    category: Mapped[DealCategory] = mapped_column(
        Enum(DealCategory), default=DealCategory.OTHER, index=True
    )

    # ── Pricing ───────────────────────────────────────────────
    deal_price: Mapped[Optional[float]] = mapped_column(Float)
    original_price: Mapped[Optional[float]] = mapped_column(Float)
    discount_percent: Mapped[Optional[float]] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(3), default="GBP")

    # ── Community signals (HotUKDeals specific) ───────────────
    hot_score: Mapped[Optional[int]] = mapped_column(Integer)
    comment_count: Mapped[Optional[int]] = mapped_column(Integer)
    vote_count: Mapped[Optional[int]] = mapped_column(Integer)

    # ── State ─────────────────────────────────────────────────
    status: Mapped[DealStatus] = mapped_column(
        Enum(DealStatus), default=DealStatus.PENDING, index=True
    )
    is_expired: Mapped[bool] = mapped_column(Boolean, default=False)

    # ── Timestamps ────────────────────────────────────────────
    deal_posted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # ── Relationships ─────────────────────────────────────────
    opportunity: Mapped[Optional["Opportunity"]] = relationship(  # noqa: F821
        back_populates="deal", uselist=False, lazy="select"
    )

    def __repr__(self) -> str:
        return f"<Deal id={self.id} source={self.source} title={self.title[:40]!r}>"
