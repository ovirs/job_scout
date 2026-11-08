"""draft survivals: how much of the last LLM draft survived into each letter sent

Each move to Applied made before this migration gets its ratio from the drafts as they
were at the move: the letter sent is the latest draft made before it and not deleted by
then, and the LLM draft is the latest such draft the LLM wrote.

Revision ID: 0015
Revises: 0014
Create Date: 2026-11-08 12:00:00.000000
"""

from collections.abc import Sequence
from difflib import SequenceMatcher

import sqlalchemy as sa
from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# The latest draft live at the move to Applied `c`, of the origins given
LIVE_AT_MOVE = """(
    SELECT d.text FROM cover_letter_drafts d
    WHERE d.application_id = c.application_id
      AND d.created_at < c.changed_at
      AND (d.deleted_at IS NULL OR d.deleted_at > c.changed_at)
      AND d.origin IN ({origins})
    ORDER BY d.id DESC
    LIMIT 1
)"""
ANY_ORIGIN = "'generated', 'revised_in_words', 'edited_by_hand'"
LLM_ORIGIN = "'generated', 'revised_in_words'"


def upgrade() -> None:
    op.create_table(
        "draft_survivals",
        sa.Column("state_change_id", sa.Integer(), nullable=False),
        sa.Column("ratio", sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(["state_change_id"], ["application_state_changes.id"]),
        sa.PrimaryKeyConstraint("state_change_id"),
    )
    connection = op.get_bind()
    moves = connection.execute(
        sa.text(
            f"SELECT c.id, {LIVE_AT_MOVE.format(origins=LLM_ORIGIN)},"
            f" {LIVE_AT_MOVE.format(origins=ANY_ORIGIN)}"
            " FROM application_state_changes c WHERE c.state = 'applied' ORDER BY c.id"
        )
    ).all()
    for state_change_id, llm_text, sent_text in moves:
        if llm_text is None:
            continue
        # As the Cover Letter package measures it, at the time of this migration
        ratio = SequenceMatcher(None, llm_text.split(), sent_text.split(), autojunk=False).ratio()
        connection.execute(
            sa.text("INSERT INTO draft_survivals (state_change_id, ratio) VALUES (:id, :ratio)"),
            {"id": state_change_id, "ratio": ratio},
        )


def downgrade() -> None:
    op.drop_table("draft_survivals")
