"""cover letter drafts

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-19 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "cover_letter_generations", sa.Column("revised_draft_id", sa.Integer(), nullable=True)
    )
    op.create_foreign_key(
        "cover_letter_generations_revised_draft_id_fkey",
        "cover_letter_generations",
        "cover_letter_drafts",
        ["revised_draft_id"],
        ["id"],
    )
    op.add_column(
        "cover_letter_drafts", sa.Column("restored_from_draft_id", sa.Integer(), nullable=True)
    )
    op.create_foreign_key(
        "cover_letter_drafts_restored_from_draft_id_fkey",
        "cover_letter_drafts",
        "cover_letter_drafts",
        ["restored_from_draft_id"],
        ["id"],
    )

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


def downgrade() -> None:
    op.drop_constraint(
        "application_state_changes_sent_draft_id_fkey",
        "application_state_changes",
        type_="foreignkey",
    )
    op.drop_column("application_state_changes", "sent_draft_id")
    op.drop_constraint(
        "cover_letter_drafts_restored_from_draft_id_fkey",
        "cover_letter_drafts",
        type_="foreignkey",
    )
    op.drop_column("cover_letter_drafts", "restored_from_draft_id")
    op.drop_constraint(
        "cover_letter_generations_revised_draft_id_fkey",
        "cover_letter_generations",
        type_="foreignkey",
    )
    op.drop_column("cover_letter_generations", "revised_draft_id")
