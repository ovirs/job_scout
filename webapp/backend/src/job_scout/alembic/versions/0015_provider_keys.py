"""provider keys

Revision ID: 0015
Revises: 0014
Create Date: 2026-11-08 10:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "provider_keys",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(), nullable=False),
        sa.Column("api_key", sa.String(), nullable=False),
        sa.Column("saved_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("owner_id", "provider"),
    )
    op.create_index(op.f("ix_provider_keys_owner_id"), "provider_keys", ["owner_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_provider_keys_owner_id"), table_name="provider_keys")
    op.drop_table("provider_keys")
