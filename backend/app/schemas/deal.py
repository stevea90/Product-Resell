"""
Pydantic schemas for API request/response validation.
Separate from DB models — allows independent evolution.
"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class OpportunitySchema(BaseModel):
    score: Optional[int]
    confidence_level: Optional[str]
    buy_price: Optional[float]
    sell_price: Optional[float]
    net_profit: Optional[float]
    roi_percent: Optional[float]
    margin_percent: Optional[float]
    fba_fee: Optional[float]
    amazon_referral_fee: Optional[float]
    shipping_cost: Optional[float]
    estimated_payout: Optional[float]
    score_reasoning: Optional[str]
    tags: Optional[list[str]]

    model_config = {"from_attributes": True}

    @classmethod
    def from_orm_with_tags(cls, obj):
        data = {
            "score": obj.score,
            "confidence_level": obj.confidence_level,
            "buy_price": obj.buy_price,
            "sell_price": obj.sell_price,
            "net_profit": obj.net_profit,
            "roi_percent": obj.roi_percent,
            "margin_percent": obj.margin_percent,
            "fba_fee": obj.fba_fee,
            "amazon_referral_fee": obj.amazon_referral_fee,
            "shipping_cost": obj.shipping_cost,
            "estimated_payout": obj.estimated_payout,
            "score_reasoning": obj.score_reasoning,
            "tags": obj.tags.split(",") if obj.tags else [],
        }
        return cls(**data)


class AmazonProductSchema(BaseModel):
    asin: Optional[str]
    amazon_url: Optional[str]
    current_price: Optional[float]
    buy_box_price: Optional[float]
    sales_rank: Optional[int]
    estimated_monthly_sales: Optional[int]
    review_count: Optional[int]
    review_rating: Optional[float]
    buy_box_seller_count: Optional[int]
    is_amazon_selling: bool = False
    fba_seller_count: Optional[int]

    model_config = {"from_attributes": True}


class DealResponse(BaseModel):
    id: int
    source: str
    title: str
    deal_price: Optional[float]
    original_price: Optional[float]
    discount_percent: Optional[float]
    currency: str
    category: Optional[str]
    image_url: Optional[str]
    source_url: str
    product_url: Optional[str]
    retailer: Optional[str]
    hot_score: Optional[int]
    comment_count: Optional[int]
    status: str
    first_seen_at: datetime
    opportunity: Optional[OpportunitySchema]
    amazon_product: Optional[AmazonProductSchema]

    model_config = {"from_attributes": True}


class DealListResponse(BaseModel):
    items: list[DealResponse]
    total: int
    page: int
    page_size: int
    pages: int


class StatsResponse(BaseModel):
    total_deals: int
    scored_deals: int
    high_confidence_opportunities: int
    avg_roi_percent: Optional[float]
    top_categories: dict[str, int]
    deals_today: int
