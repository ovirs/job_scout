"""Procrastinate's queue schema

The schema of Procrastinate 3.10.0, vendored so a fresh database always gets
the same tables whatever Procrastinate version is installed. Upgrading
Procrastinate means a new revision applying its SQL migrations newer than
03.04.00 (procrastinate/sql/migrations).

Revision ID: 0001
Revises:
Create Date: 2026-10-14
"""

from collections.abc import Sequence
from pathlib import Path

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = Path(__file__).with_name("procrastinate_schema_3_10_0.sql")


def upgrade() -> None:
    op.execute(SCHEMA.read_text(encoding="utf-8"))


def downgrade() -> None:
    raise NotImplementedError("Procrastinate's schema is not removed")
