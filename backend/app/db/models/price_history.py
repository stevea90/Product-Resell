"""
Price history for an Amazon product — populated from Keepa data.
Used by the scoring engine to detect price volatility and stability.
"""
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Float, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class PriceHistory(Base):
    __tablename__ = "price_history"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    amazon_product_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("amazon_products.id", ondelete="CASCADE"), index=True
    )
    price_type: Mapped[str] = mapped_column(String(30))  # "amazon" | "new" | "used"
    price: Mapped[float] = mapped_column(Float, nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    inserted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    amazon_product: Mapped["AmazonProduct"] = relationship(  # noqa: F821
        back_populates="price_history"
    )
