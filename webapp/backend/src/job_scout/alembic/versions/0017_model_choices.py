"""step defaults, and the model choice stored on every run

Every run so far called Anthropic, with the model it stored, so each run that called the
LLM is filled in as requested from, and answered by, Anthropic with that model. A run that
never called it has no model to record, so its choice is left empty, whole.

Revision ID: 0017
Revises: 0016
Create Date: 2026-11-08 18:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RUN_TABLES = ["clippings", "evaluations", "cover_letter_generations"]


def upgrade() -> None:
    op.create_table(
        "step_defaults",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("step", sa.String(), nullable=False),
        sa.Column("provider", sa.String(), nullable=False),
        sa.Column("model_id", sa.String(), nullable=False),
        sa.Column("effort", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("owner_id", "step"),
    )
    op.create_index(op.f("ix_step_defaults_owner_id"), "step_defaults", ["owner_id"], unique=False)
    for table in RUN_TABLES:
        op.add_column(table, sa.Column("requested_provider", sa.String(), nullable=True))
        op.add_column(table, sa.Column("requested_model", sa.String(), nullable=True))
        op.add_column(table, sa.Column("requested_effort", sa.String(), nullable=True))
        op.add_column(table, sa.Column("provider", sa.String(), nullable=True))
        op.execute(
            f"UPDATE {table} SET requested_provider = 'anthropic', requested_model = model,"
            " provider = 'anthropic' WHERE model IS NOT NULL"
        )


def downgrade() -> None:
    for table in RUN_TABLES:
        op.drop_column(table, "provider")
        op.drop_column(table, "requested_effort")
        op.drop_column(table, "requested_model")
        op.drop_column(table, "requested_provider")
    op.drop_index(op.f("ix_step_defaults_owner_id"), table_name="step_defaults")
    op.drop_table("step_defaults")
