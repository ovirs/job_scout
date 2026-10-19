"""cover letters

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-18 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "cover_letter_drafts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("application_id", sa.Integer(), nullable=False),
        sa.Column("origin", sa.String(), nullable=False),
        sa.Column("text", sa.String(), nullable=False),
        sa.Column("instruction", sa.String(), nullable=True),
        sa.Column(
            "unsupported_requirements", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("model", sa.String(), nullable=True),
        sa.Column("prompt_version", sa.String(), nullable=True),
        sa.Column("career_profile_version_id", sa.Integer(), nullable=True),
        sa.Column("writing_guide_version_id", sa.Integer(), nullable=True),
        sa.Column("evaluation_id", sa.Integer(), nullable=True),
        sa.Column("evaluation_case", sa.String(), nullable=True),
        sa.Column("content_hash", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["application_id"], ["applications.id"]),
        sa.ForeignKeyConstraint(["career_profile_version_id"], ["document_versions.id"]),
        sa.ForeignKeyConstraint(["evaluation_id"], ["evaluations.id"]),
        sa.ForeignKeyConstraint(["writing_guide_version_id"], ["document_versions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_cover_letter_drafts_application_id"),
        "cover_letter_drafts",
        ["application_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_cover_letter_drafts_owner_id"), "cover_letter_drafts", ["owner_id"], unique=False
    )
    op.create_table(
        "cover_letter_generations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("application_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("instruction", sa.String(), nullable=True),
        sa.Column("evaluation_id", sa.Integer(), nullable=True),
        sa.Column("evaluation_case", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_kind", sa.String(), nullable=True),
        sa.Column("failure_reason", sa.String(), nullable=True),
        sa.Column("draft_id", sa.Integer(), nullable=True),
        sa.CheckConstraint(
            "(failure_kind IS NULL) = (failure_reason IS NULL)", name="failure_complete"
        ),
        sa.CheckConstraint(
            "(evaluation_case = 'missing') = (evaluation_id IS NULL)", name="evaluation_case"
        ),
        sa.ForeignKeyConstraint(["application_id"], ["applications.id"]),
        sa.ForeignKeyConstraint(["draft_id"], ["cover_letter_drafts.id"]),
        sa.ForeignKeyConstraint(["evaluation_id"], ["evaluations.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_cover_letter_generations_application_id"),
        "cover_letter_generations",
        ["application_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_cover_letter_generations_owner_id"),
        "cover_letter_generations",
        ["owner_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_cover_letter_generations_owner_id"), table_name="cover_letter_generations"
    )
    op.drop_index(
        op.f("ix_cover_letter_generations_application_id"), table_name="cover_letter_generations"
    )
    op.drop_table("cover_letter_generations")
    op.drop_index(op.f("ix_cover_letter_drafts_owner_id"), table_name="cover_letter_drafts")
    op.drop_index(op.f("ix_cover_letter_drafts_application_id"), table_name="cover_letter_drafts")
    op.drop_table("cover_letter_drafts")
