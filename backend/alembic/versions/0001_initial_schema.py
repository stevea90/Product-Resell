"""Initial schema — deals, amazon_products, opportunities, price_history, scrape_runs

Revision ID: 0001
Revises:
Create Date: 2025-06-06
"""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── deals ─────────────────────────────────────────────────────────────
    op.create_table(
        "deals",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("source", sa.Enum(
            "hotukdeals", "smyths", "argos", "currys", "manual",
            name="dealsource"
        ), nullable=False),
        sa.Column("source_id", sa.String(255), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("retailer", sa.String(255), nullable=True),
        sa.Column("product_url", sa.Text(), nullable=True),
        sa.Column("image_url", sa.Text(), nullable=True),
        sa.Column("category", sa.Enum(
            "toys", "lego", "gaming", "electronics", "other",
            name="dealcategory"
        ), nullable=True),
        sa.Column("deal_price", sa.Float(), nullable=True),
        sa.Column("original_price", sa.Float(), nullable=True),
        sa.Column("discount_percent", sa.Float(), nullable=True),
        sa.Column("currency", sa.String(3), nullable=True),
        sa.Column("hot_score", sa.Integer(), nullable=True),
        sa.Column("comment_count", sa.Integer(), nullable=True),
        sa.Column("vote_count", sa.Integer(), nullable=True),
        sa.Column("status", sa.Enum(
            "pending", "enriching", "scored", "ignored", "expired",
            name="dealstatus"
        ), nullable=True),
        sa.Column("is_expired", sa.Boolean(), nullable=True),
        sa.Column("deal_posted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_url", name="uq_deals_source_url"),
    )
    op.create_index("ix_deals_source", "deals", ["source"])
    op.create_index("ix_deals_source_id", "deals", ["source_id"])
    op.create_index("ix_deals_category", "deals", ["category"])
    op.create_index("ix_deals_status", "deals", ["status"])

    # ── amazon_products ───────────────────────────────────────────────────
    op.create_table(
        "amazon_products",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("deal_id", sa.BigInteger(), nullable=False),
        sa.Column("asin", sa.String(20), nullable=True),
        sa.Column("amazon_url", sa.Text(), nullable=True),
        sa.Column("title", sa.String(512), nullable=True),
        sa.Column("brand", sa.String(255), nullable=True),
        sa.Column("model_number", sa.String(255), nullable=True),
        sa.Column("current_price", sa.Float(), nullable=True),
        sa.Column("lowest_price_30d", sa.Float(), nullable=True),
        sa.Column("highest_price_30d", sa.Float(), nullable=True),
        sa.Column("lowest_price_90d", sa.Float(), nullable=True),
        sa.Column("buy_box_price", sa.Float(), nullable=True),
        sa.Column("buy_box_seller_count", sa.Integer(), nullable=True),
        sa.Column("is_amazon_selling", sa.Boolean(), nullable=True),
        sa.Column("fba_seller_count", sa.Integer(), nullable=True),
        sa.Column("sales_rank", sa.Integer(), nullable=True),
        sa.Column("sales_rank_category", sa.String(255), nullable=True),
        sa.Column("estimated_monthly_sales", sa.Integer(), nullable=True),
        sa.Column("review_count", sa.Integer(), nullable=True),
        sa.Column("review_rating", sa.Float(), nullable=True),
        sa.Column("fba_fee_estimate", sa.Float(), nullable=True),
        sa.Column("referral_fee_estimate", sa.Float(), nullable=True),
        sa.Column("referral_fee_percent", sa.Float(), nullable=True),
        sa.Column("weight_kg", sa.Float(), nullable=True),
        sa.Column("length_cm", sa.Float(), nullable=True),
        sa.Column("width_cm", sa.Float(), nullable=True),
        sa.Column("height_cm", sa.Float(), nullable=True),
        sa.Column("data_source", sa.String(50), nullable=True),
        sa.Column("match_confidence", sa.Float(), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["deal_id"], ["deals.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("deal_id"),
    )
    op.create_index("ix_amazon_products_deal_id", "amazon_products", ["deal_id"])
    op.create_index("ix_amazon_products_asin", "amazon_products", ["asin"])

    # ── opportunities ─────────────────────────────────────────────────────
    op.create_table(
        "opportunities",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("deal_id", sa.BigInteger(), nullable=False),
        sa.Column("buy_price", sa.Float(), nullable=True),
        sa.Column("sell_price", sa.Float(), nullable=True),
        sa.Column("gross_profit", sa.Float(), nullable=True),
        sa.Column("net_profit", sa.Float(), nullable=True),
        sa.Column("roi_percent", sa.Float(), nullable=True),
        sa.Column("margin_percent", sa.Float(), nullable=True),
        sa.Column("break_even_price", sa.Float(), nullable=True),
        sa.Column("estimated_payout", sa.Float(), nullable=True),
        sa.Column("amazon_referral_fee", sa.Float(), nullable=True),
        sa.Column("fba_fee", sa.Float(), nullable=True),
        sa.Column("vat_amount", sa.Float(), nullable=True),
        sa.Column("shipping_cost", sa.Float(), nullable=True),
        sa.Column("total_costs", sa.Float(), nullable=True),
        sa.Column("score", sa.Integer(), nullable=True),
        sa.Column("confidence_level", sa.String(20), nullable=True),
        sa.Column("score_roi", sa.Float(), nullable=True),
        sa.Column("score_demand", sa.Float(), nullable=True),
        sa.Column("score_competition", sa.Float(), nullable=True),
        sa.Column("score_reviews", sa.Float(), nullable=True),
        sa.Column("score_price_stability", sa.Float(), nullable=True),
        sa.Column("score_community", sa.Float(), nullable=True),
        sa.Column("score_reasoning", sa.Text(), nullable=True),
        sa.Column("tags", sa.String(512), nullable=True),
        sa.Column("alert_sent", sa.Boolean(), nullable=True),
        sa.Column("alert_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("scored_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["deal_id"], ["deals.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("deal_id"),
    )
    op.create_index("ix_opportunities_deal_id", "opportunities", ["deal_id"])
    op.create_index("ix_opportunities_score", "opportunities", ["score"])

    # ── price_history ─────────────────────────────────────────────────────
    op.create_table(
        "price_history",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("amazon_product_id", sa.BigInteger(), nullable=False),
        sa.Column("price_type", sa.String(30), nullable=True),
        sa.Column("price", sa.Float(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("inserted_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["amazon_product_id"], ["amazon_products.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_price_history_amazon_product_id", "price_history", ["amazon_product_id"])
    op.create_index("ix_price_history_recorded_at", "price_history", ["recorded_at"])

    # ── scrape_runs ───────────────────────────────────────────────────────
    op.create_table(
        "scrape_runs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("source", sa.String(50), nullable=False),
        sa.Column("status", sa.String(20), nullable=True),
        sa.Column("deals_found", sa.Integer(), nullable=True),
        sa.Column("deals_new", sa.Integer(), nullable=True),
        sa.Column("deals_duplicate", sa.Integer(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_seconds", sa.Float(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_scrape_runs_source", "scrape_runs", ["source"])


def downgrade() -> None:
    op.drop_table("scrape_runs")
    op.drop_table("price_history")
    op.drop_table("opportunities")
    op.drop_table("amazon_products")
    op.drop_table("deals")
    op.execute("DROP TYPE IF EXISTS dealsource")
    op.execute("DROP TYPE IF EXISTS dealcategory")
    op.execute("DROP TYPE IF EXISTS dealstatus")
