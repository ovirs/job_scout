"""evaluations

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-16 14:07:45.733673
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "evaluations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("job_posting_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("model", sa.String(), nullable=True),
        sa.Column("prompt_version", sa.String(), nullable=True),
        sa.Column("career_profile_version_id", sa.Integer(), nullable=True),
        sa.Column("preferences_version_id", sa.Integer(), nullable=True),
        sa.Column("deal_breaker_set_version_id", sa.Integer(), nullable=True),
        sa.Column("content_hash", sa.String(), nullable=True),
        sa.Column("failure_kind", sa.String(), nullable=True),
        sa.Column("failure_reason", sa.String(), nullable=True),
        sa.Column("result", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("recommendation", sa.String(), nullable=True),
        sa.Column("llm_recommendation", sa.String(), nullable=True),
        sa.Column("disqualified_but_recommended", sa.Boolean(), nullable=True),
        sa.CheckConstraint(
            "(failure_kind IS NULL) = (failure_reason IS NULL)", name="failure_complete"
        ),
        sa.ForeignKeyConstraint(
            ["career_profile_version_id"],
            ["document_versions.id"],
        ),
        sa.ForeignKeyConstraint(
            ["deal_breaker_set_version_id"],
            ["deal_breaker_set_versions.id"],
        ),
        sa.ForeignKeyConstraint(
            ["job_posting_id"],
            ["job_postings.id"],
        ),
        sa.ForeignKeyConstraint(
            ["preferences_version_id"],
            ["document_versions.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_evaluations_job_posting_id"), "evaluations", ["job_posting_id"], unique=False
    )
    op.create_index(op.f("ix_evaluations_owner_id"), "evaluations", ["owner_id"], unique=False)
    op.drop_column("job_postings", "processed_at")


def downgrade() -> None:
    op.add_column(
        "job_postings",
        sa.Column(
            "processed_at", postgresql.TIMESTAMP(timezone=True), autoincrement=False, nullable=True
        ),
    )
    op.drop_index(op.f("ix_evaluations_owner_id"), table_name="evaluations")
    op.drop_index(op.f("ix_evaluations_job_posting_id"), table_name="evaluations")
    op.drop_table("evaluations")
