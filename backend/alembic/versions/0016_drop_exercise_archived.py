"""drop exercise archive flag

Revision ID: 0016
Revises: 0015
Create Date: 2026-11-07

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0016"
down_revision: str | Sequence[str] | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_column("exercises", "archived")


def downgrade() -> None:
    op.add_column(
        "exercises",
        sa.Column("archived", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
