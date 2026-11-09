"""model listings, hidden models and model options

Revision ID: 0016
Revises: 0015
Create Date: 2026-11-08 14:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "model_listings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("models", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("owner_id", "provider"),
    )
    op.create_index(
        op.f("ix_model_listings_owner_id"), "model_listings", ["owner_id"], unique=False
    )
    op.create_table(
        "hidden_models",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(), nullable=False),
        sa.Column("model_id", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("owner_id", "provider", "model_id"),
    )
    op.create_index(op.f("ix_hidden_models_owner_id"), "hidden_models", ["owner_id"], unique=False)
    op.create_table(
        "model_options",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("show_snapshots", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("owner_id"),
    )


def downgrade() -> None:
    op.drop_table("model_options")
    op.drop_index(op.f("ix_hidden_models_owner_id"), table_name="hidden_models")
    op.drop_table("hidden_models")
    op.drop_index(op.f("ix_model_listings_owner_id"), table_name="model_listings")
    op.drop_table("model_listings")
