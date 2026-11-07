"""draft survivals: how much of the last LLM draft survived into the letter sent

Revision ID: 0015
Revises: 0014
Create Date: 2026-11-06 12:00:00.000000
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
        "draft_survivals",
        sa.Column("state_change_id", sa.Integer(), nullable=False),
        sa.Column("ratio", sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(["state_change_id"], ["application_state_changes.id"]),
        sa.PrimaryKeyConstraint("state_change_id"),
    )


def downgrade() -> None:
    op.drop_table("draft_survivals")
