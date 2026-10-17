"""triages

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-16 16:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "triages",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("job_posting_id", sa.Integer(), nullable=False),
        sa.Column("value", sa.String(), nullable=False),
        sa.Column("origin", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "changed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["job_posting_id"], ["job_postings.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("job_posting_id"),
    )
    op.create_index(op.f("ix_triages_owner_id"), "triages", ["owner_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_triages_owner_id"), table_name="triages")
    op.drop_table("triages")
