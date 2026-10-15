"""job postings

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-14 16:44:04.297424
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "job_postings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("source_posting_id", sa.String(), nullable=False),
        sa.Column("company", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("location_text", sa.String(), nullable=True),
        sa.Column("workplace_type", sa.String(), nullable=True),
        sa.Column("description", sa.String(), nullable=False),
        sa.Column("url", sa.String(), nullable=True),
        sa.Column("content_hash", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("extracted_fields", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("ats", sa.String(), nullable=True),
        sa.Column("ats_board", sa.String(), nullable=True),
        sa.Column("ats_posting_id", sa.String(), nullable=True),
        sa.Column("raw_ats_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("screening_scores", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("screened_in", sa.Boolean(), nullable=True),
        sa.Column("repost_of_id", sa.Integer(), nullable=True),
        sa.Column("duplicate_of_id", sa.Integer(), nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "(ats IS NULL) = (ats_board IS NULL) AND (ats IS NULL) = (ats_posting_id IS NULL)",
            name="ats_key_complete",
        ),
        sa.ForeignKeyConstraint(
            ["duplicate_of_id"],
            ["job_postings.id"],
        ),
        sa.ForeignKeyConstraint(
            ["repost_of_id"],
            ["job_postings.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ats", "ats_board", "ats_posting_id"),
    )
    op.create_index(op.f("ix_job_postings_owner_id"), "job_postings", ["owner_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_job_postings_owner_id"), table_name="job_postings")
    op.drop_table("job_postings")
