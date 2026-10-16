"""manual entry confirmation

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-16 10:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("job_postings", sa.Column("pasted_text", sa.String(), nullable=True))
    op.add_column("clippings", sa.Column("job_posting_id", sa.Integer(), nullable=True))
    op.create_unique_constraint(
        op.f("clippings_job_posting_id_key"), "clippings", ["job_posting_id"]
    )
    op.create_foreign_key(
        op.f("clippings_job_posting_id_fkey"),
        "clippings",
        "job_postings",
        ["job_posting_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint(op.f("clippings_job_posting_id_fkey"), "clippings", type_="foreignkey")
    op.drop_constraint(op.f("clippings_job_posting_id_key"), "clippings", type_="unique")
    op.drop_column("clippings", "job_posting_id")
    op.drop_column("job_postings", "pasted_text")
