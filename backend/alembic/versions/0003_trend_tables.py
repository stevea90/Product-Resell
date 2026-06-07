"""Create demand trend detection tables

Revision ID: 0003
Revises: 0002
Create Date: 2026-06-07
"""
import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "product_metrics",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("asin", sa.String(20), nullable=False),
        sa.Column("product_title", sa.String(500), nullable=True),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("signal_type", sa.String(50), nullable=False),
        sa.Column("value", sa.Float(), nullable=True),
        sa.Column("source", sa.String(50), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("asin", "date", "signal_type", name="uq_metric_asin_date_signal"),
    )
    op.create_index("ix_product_metrics_asin", "product_metrics", ["asin"])
    op.create_index("ix_product_metrics_date", "product_metrics", ["date"])

    op.create_table(
        "product_trends",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("asin", sa.String(20), nullable=False),
        sa.Column("product_title", sa.String(500), nullable=True),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("demand_score", sa.Float(), nullable=True),
        sa.Column("trend_direction", sa.String(20), nullable=True),
        sa.Column("ma_7d", sa.Float(), nullable=True),
        sa.Column("ma_30d", sa.Float(), nullable=True),
        sa.Column("z_score", sa.Float(), nullable=True),
        sa.Column("signal_breakdown", sa.JSON(), nullable=True),
        sa.Column("computed_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("asin", "date", name="uq_trend_asin_date"),
    )
    op.create_index("ix_product_trends_asin", "product_trends", ["asin"])
    op.create_index("ix_product_trends_date", "product_trends", ["date"])

    op.create_table(
        "trend_anomalies",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("asin", sa.String(20), nullable=False),
        sa.Column("product_title", sa.String(500), nullable=True),
        sa.Column("detected_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("signal_type", sa.String(50), nullable=False),
        sa.Column("z_score", sa.Float(), nullable=True),
        sa.Column("severity", sa.String(20), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("current_value", sa.Float(), nullable=True),
        sa.Column("baseline_value", sa.Float(), nullable=True),
        sa.Column("is_acknowledged", sa.Boolean(), nullable=False, server_default="false"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_trend_anomalies_asin", "trend_anomalies", ["asin"])
    op.create_index("ix_trend_anomalies_detected_at", "trend_anomalies", ["detected_at"])


def downgrade() -> None:
    op.drop_table("trend_anomalies")
    op.drop_table("product_trends")
    op.drop_table("product_metrics")
