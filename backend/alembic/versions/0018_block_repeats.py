"""block placement can repeat without an end date

Revision ID: 0018
Revises: 0017
Create Date: 2026-11-08

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0018"
down_revision: str | Sequence[str] | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "block_placements",
        sa.Column("repeats", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.alter_column("block_placements", "repeats", server_default=None)
    op.alter_column("block_placements", "end_date", existing_type=sa.Date(), nullable=True)
    op.drop_constraint("ck_block_placements_dates", "block_placements", type_="check")
    op.create_check_constraint(
        "ck_block_placements_dates",
        "block_placements",
        "(repeats = false AND end_date IS NOT NULL AND end_date >= start_date) "
        "OR (repeats = true AND end_date IS NULL)",
    )


def downgrade() -> None:
    op.execute("UPDATE block_placements SET end_date = start_date WHERE end_date IS NULL")
    op.drop_constraint("ck_block_placements_dates", "block_placements", type_="check")
    op.alter_column("block_placements", "end_date", existing_type=sa.Date(), nullable=False)
    op.drop_column("block_placements", "repeats")
    op.create_check_constraint(
        "ck_block_placements_dates",
        "block_placements",
        "end_date >= start_date",
    )
