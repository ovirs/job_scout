"""one LLM run lifecycle: the same statuses, timestamps and failure columns

Revision ID: 0013
Revises: 0012
Create Date: 2026-11-04 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RUN_TABLES = ["clippings", "evaluations", "cover_letter_generations"]


def upgrade() -> None:
    for table in RUN_TABLES:
        op.add_column(
            table,
            sa.Column(
                "queued_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
        )
        op.execute(f"UPDATE {table} SET queued_at = created_at")

    op.add_column("clippings", sa.Column("started_at", sa.DateTime(timezone=True)))
    op.add_column("clippings", sa.Column("finished_at", sa.DateTime(timezone=True)))
    op.execute("UPDATE clippings SET status = 'queued' WHERE status = 'pending'")

    op.execute("UPDATE evaluations SET status = 'failed' WHERE status = 'not_evaluated'")

    op.add_column("cover_letter_generations", sa.Column("model", sa.String()))
    op.add_column("cover_letter_generations", sa.Column("prompt_version", sa.String()))


def downgrade() -> None:
    op.drop_column("cover_letter_generations", "prompt_version")
    op.drop_column("cover_letter_generations", "model")

    op.execute("UPDATE evaluations SET status = 'not_evaluated' WHERE status = 'failed'")

    op.execute("UPDATE clippings SET status = 'pending' WHERE status IN ('queued', 'running')")
    op.drop_column("clippings", "finished_at")
    op.drop_column("clippings", "started_at")

    for table in RUN_TABLES:
        op.drop_column(table, "queued_at")
