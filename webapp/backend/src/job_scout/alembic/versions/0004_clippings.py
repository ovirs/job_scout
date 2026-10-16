"""clippings

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-15 18:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "clippings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("pasted_text", sa.String(), nullable=False),
        sa.Column("url", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("model", sa.String(), nullable=True),
        sa.Column("prompt_version", sa.String(), nullable=True),
        sa.Column("failure_kind", sa.String(), nullable=True),
        sa.Column("failure_reason", sa.String(), nullable=True),
        sa.Column("extraction", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("description_cut", sa.Boolean(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_clippings_owner_id"), "clippings", ["owner_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_clippings_owner_id"), table_name="clippings")
    op.drop_table("clippings")
