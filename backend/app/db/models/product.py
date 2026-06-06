"""
AmazonProduct represents the enriched Amazon listing data for a deal.
One deal → one Amazon product (best match found).
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
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


class AmazonProduct(Base):
    __tablename__ = "amazon_products"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    deal_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("deals.id", ondelete="CASCADE"), unique=True, index=True
    )

    # ── Amazon identifiers ────────────────────────────────────
    asin: Mapped[Optional[str]] = mapped_column(String(20), index=True)
    amazon_url: Mapped[Optional[str]] = mapped_column(Text)
    title: Mapped[Optional[str]] = mapped_column(String(512))
    brand: Mapped[Optional[str]] = mapped_column(String(255))
    model_number: Mapped[Optional[str]] = mapped_column(String(255))

    # ── Pricing ───────────────────────────────────────────────
    current_price: Mapped[Optional[float]] = mapped_column(Float)
    lowest_price_30d: Mapped[Optional[float]] = mapped_column(Float)
    highest_price_30d: Mapped[Optional[float]] = mapped_column(Float)
    lowest_price_90d: Mapped[Optional[float]] = mapped_column(Float)
    buy_box_price: Mapped[Optional[float]] = mapped_column(Float)

    # ── Competition ───────────────────────────────────────────
    buy_box_seller_count: Mapped[Optional[int]] = mapped_column(Integer)
    is_amazon_selling: Mapped[bool] = mapped_column(Boolean, default=False)
    fba_seller_count: Mapped[Optional[int]] = mapped_column(Integer)

    # ── Demand signals ────────────────────────────────────────
    sales_rank: Mapped[Optional[int]] = mapped_column(Integer)
    sales_rank_category: Mapped[Optional[str]] = mapped_column(String(255))
    estimated_monthly_sales: Mapped[Optional[int]] = mapped_column(Integer)
    review_count: Mapped[Optional[int]] = mapped_column(Integer)
    review_rating: Mapped[Optional[float]] = mapped_column(Float)

    # ── Fees (FBA) ────────────────────────────────────────────
    fba_fee_estimate: Mapped[Optional[float]] = mapped_column(Float)
    referral_fee_estimate: Mapped[Optional[float]] = mapped_column(Float)
    referral_fee_percent: Mapped[Optional[float]] = mapped_column(Float)

    # ── Product dimensions (for accurate fee calc) ────────────
    weight_kg: Mapped[Optional[float]] = mapped_column(Float)
    length_cm: Mapped[Optional[float]] = mapped_column(Float)
    width_cm: Mapped[Optional[float]] = mapped_column(Float)
    height_cm: Mapped[Optional[float]] = mapped_column(Float)

    # ── Data provenance ───────────────────────────────────────
    data_source: Mapped[Optional[str]] = mapped_column(String(50))  # "keepa" | "scrape"
    match_confidence: Mapped[Optional[float]] = mapped_column(Float)  # 0–1

    # ── Timestamps ────────────────────────────────────────────
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # ── Relationships ─────────────────────────────────────────
    price_history: Mapped[list["PriceHistory"]] = relationship(  # noqa: F821
        back_populates="amazon_product", lazy="select"
    )

    def __repr__(self) -> str:
        return f"<AmazonProduct asin={self.asin} price={self.current_price}>"
