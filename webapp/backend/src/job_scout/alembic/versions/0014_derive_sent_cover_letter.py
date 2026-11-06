"""derive the Cover Letter sent from the drafts, dropping the pointer on the state change

The letter sent on a move to Applied is the latest draft made before the move and not
deleted by then: no draft is made or deleted while the Cover Letter is locked. The
upgrade first checks that this gives the draft each move recorded, and refuses to run
otherwise, so the letter shown as sent never changes.

Revision ID: 0014
Revises: 0013
Create Date: 2026-11-05 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# The draft sent on the move to Applied `c`, as the Cover Letter package derives it
DERIVED_SENT_DRAFT = """(
    SELECT d.id FROM cover_letter_drafts d
    WHERE d.application_id = c.application_id
      AND d.created_at < c.changed_at
      AND (d.deleted_at IS NULL OR d.deleted_at > c.changed_at)
    ORDER BY d.id DESC
    LIMIT 1
)"""


def upgrade() -> None:
    differing = (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT c.id FROM application_state_changes c WHERE"
                f" c.sent_draft_id IS DISTINCT FROM (CASE WHEN c.state = 'applied'"
                f" THEN {DERIVED_SENT_DRAFT} END) ORDER BY c.id"
            )
        )
        .scalars()
        .all()
    )
    if differing:
        raise RuntimeError(
            "The Cover Letter sent on these Application state changes is not the latest"
            f" draft made before them and not deleted by then: {differing}. Fix their"
            " sent_draft_id or the drafts' timestamps, then migrate again."
        )
    op.drop_constraint(
        "application_state_changes_sent_draft_id_fkey",
        "application_state_changes",
        type_="foreignkey",
    )
    op.drop_column("application_state_changes", "sent_draft_id")


def downgrade() -> None:
    op.add_column(
        "application_state_changes", sa.Column("sent_draft_id", sa.Integer(), nullable=True)
    )
    op.create_foreign_key(
        "application_state_changes_sent_draft_id_fkey",
        "application_state_changes",
        "cover_letter_drafts",
        ["sent_draft_id"],
        ["id"],
    )
    op.execute(
        f"UPDATE application_state_changes c SET sent_draft_id = {DERIVED_SENT_DRAFT}"
        " WHERE c.state = 'applied'"
    )
