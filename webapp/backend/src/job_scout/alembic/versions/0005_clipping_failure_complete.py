"""clipping failure complete

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-15 19:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_check_constraint(
        "failure_complete", "clippings", "(failure_kind IS NULL) = (failure_reason IS NULL)"
    )


def downgrade() -> None:
    op.drop_constraint("failure_complete", "clippings", type_="check")
