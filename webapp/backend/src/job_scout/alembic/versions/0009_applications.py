"""applications

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-16 23:37:49.508420
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "applications",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("job_posting_id", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("copied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("copy_title", sa.String(), nullable=True),
        sa.Column("copy_company", sa.String(), nullable=True),
        sa.Column("copy_location_text", sa.String(), nullable=True),
        sa.Column("copy_description", sa.String(), nullable=True),
        sa.Column("copy_url", sa.String(), nullable=True),
        sa.Column("copy_content_hash", sa.String(), nullable=True),
        sa.CheckConstraint(
            "(copied_at IS NULL) = (copy_title IS NULL)"
            " AND (copied_at IS NULL) = (copy_company IS NULL)"
            " AND (copied_at IS NULL) = (copy_description IS NULL)"
            " AND (copied_at IS NULL) = (copy_content_hash IS NULL)",
            name="posting_copy_complete",
        ),
        sa.ForeignKeyConstraint(
            ["job_posting_id"],
            ["job_postings.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_applications_job_posting_id"), "applications", ["job_posting_id"], unique=False
    )
    op.create_index(
        "ix_applications_one_live_per_posting",
        "applications",
        ["job_posting_id"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(op.f("ix_applications_owner_id"), "applications", ["owner_id"], unique=False)
    op.create_table(
        "application_state_changes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("application_id", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(), nullable=False),
        sa.Column(
            "changed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["application_id"],
            ["applications.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_application_state_changes_application_id"),
        "application_state_changes",
        ["application_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_application_state_changes_application_id"), table_name="application_state_changes"
    )
    op.drop_table("application_state_changes")
    op.drop_index(op.f("ix_applications_owner_id"), table_name="applications")
    op.drop_index(
        "ix_applications_one_live_per_posting",
        table_name="applications",
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.drop_index(op.f("ix_applications_job_posting_id"), table_name="applications")
    op.drop_table("applications")
