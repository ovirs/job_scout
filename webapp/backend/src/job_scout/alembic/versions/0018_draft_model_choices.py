"""the Provider and effort each Cover Letter draft was made with

A generated draft takes the Provider that answered its generation and the effort that
generation asked for. A restored draft copies the draft it restores, which is older, so
the drafts are filled in from the oldest. A hand edit has neither.

Revision ID: 0018
Revises: 0017
Create Date: 2026-11-09 09:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("cover_letter_drafts", sa.Column("provider", sa.String(), nullable=True))
    op.add_column("cover_letter_drafts", sa.Column("effort", sa.String(), nullable=True))
    op.execute(
        "UPDATE cover_letter_drafts AS draft"
        " SET provider = generation.provider, effort = generation.requested_effort"
        " FROM cover_letter_generations AS generation"
        " WHERE generation.draft_id = draft.id"
    )
    restored = op.get_bind().execute(
        sa.text(
            "SELECT id, restored_from_draft_id FROM cover_letter_drafts"
            " WHERE restored_from_draft_id IS NOT NULL ORDER BY id"
        )
    )
    for draft_id, source_id in restored.all():
        op.get_bind().execute(
            sa.text(
                "UPDATE cover_letter_drafts AS draft"
                " SET provider = source.provider, effort = source.effort"
                " FROM cover_letter_drafts AS source"
                " WHERE draft.id = :draft_id AND source.id = :source_id"
            ),
            {"draft_id": draft_id, "source_id": source_id},
        )


def downgrade() -> None:
    op.drop_column("cover_letter_drafts", "effort")
    op.drop_column("cover_letter_drafts", "provider")
