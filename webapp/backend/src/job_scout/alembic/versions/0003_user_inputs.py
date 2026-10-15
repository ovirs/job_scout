"""user inputs

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-15 17:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "document_versions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("text", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("owner_id", "kind", "number"),
    )
    op.create_index(
        op.f("ix_document_versions_owner_id"), "document_versions", ["owner_id"], unique=False
    )
    op.create_table(
        "deal_breakers",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_deal_breakers_owner_id"), "deal_breakers", ["owner_id"], unique=False)
    op.create_table(
        "deal_breaker_set_versions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("owner_id", "number"),
    )
    op.create_index(
        op.f("ix_deal_breaker_set_versions_owner_id"),
        "deal_breaker_set_versions",
        ["owner_id"],
        unique=False,
    )
    op.create_table(
        "deal_breaker_set_items",
        sa.Column("set_version_id", sa.Integer(), nullable=False),
        sa.Column("deal_breaker_id", sa.Integer(), nullable=False),
        sa.Column("text", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(
            ["deal_breaker_id"],
            ["deal_breakers.id"],
        ),
        sa.ForeignKeyConstraint(
            ["set_version_id"],
            ["deal_breaker_set_versions.id"],
        ),
        sa.PrimaryKeyConstraint("set_version_id", "deal_breaker_id"),
    )


def downgrade() -> None:
    op.drop_table("deal_breaker_set_items")
    op.drop_index(
        op.f("ix_deal_breaker_set_versions_owner_id"), table_name="deal_breaker_set_versions"
    )
    op.drop_table("deal_breaker_set_versions")
    op.drop_index(op.f("ix_deal_breakers_owner_id"), table_name="deal_breakers")
    op.drop_table("deal_breakers")
    op.drop_index(op.f("ix_document_versions_owner_id"), table_name="document_versions")
    op.drop_table("document_versions")
