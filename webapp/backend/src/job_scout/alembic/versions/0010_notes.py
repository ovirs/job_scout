"""notes

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-18 10:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "notes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("job_posting_id", sa.Integer(), nullable=True),
        sa.Column("application_id", sa.Integer(), nullable=True),
        sa.Column("text", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "(job_posting_id IS NULL) <> (application_id IS NULL)",
            name="on_posting_or_application",
        ),
        sa.ForeignKeyConstraint(
            ["application_id"],
            ["applications.id"],
        ),
        sa.ForeignKeyConstraint(
            ["job_posting_id"],
            ["job_postings.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_notes_application_id"), "notes", ["application_id"], unique=False)
    op.create_index(op.f("ix_notes_job_posting_id"), "notes", ["job_posting_id"], unique=False)
    op.create_index(op.f("ix_notes_owner_id"), "notes", ["owner_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_notes_owner_id"), table_name="notes")
    op.drop_index(op.f("ix_notes_job_posting_id"), table_name="notes")
    op.drop_index(op.f("ix_notes_application_id"), table_name="notes")
    op.drop_table("notes")
