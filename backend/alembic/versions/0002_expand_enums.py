"""Expand DealSource and DealCategory enums for new retailers and categories

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-07
"""
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

_NEW_SOURCES = ["very", "lego_shop", "box", "ebuyer", "boots", "costco", "tkmaxx", "bm", "homebargains"]
_NEW_CATEGORIES = ["home", "beauty", "sports", "fashion", "garden", "health", "pets", "books"]


def upgrade() -> None:
    for value in _NEW_SOURCES:
        op.execute(f"ALTER TYPE dealsource ADD VALUE IF NOT EXISTS '{value}'")
    for value in _NEW_CATEGORIES:
        op.execute(f"ALTER TYPE dealcategory ADD VALUE IF NOT EXISTS '{value}'")


def downgrade() -> None:
    # PostgreSQL does not support removing enum values without recreating the type.
    # A full downgrade would require recreating both types — omitted for safety.
    pass
