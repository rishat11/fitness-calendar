"""block cycle length in days

Revision ID: 0017
Revises: 0016
Create Date: 2026-11-07

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0017"
down_revision: str | Sequence[str] | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "blocks",
        sa.Column("cycle_days", sa.Integer(), server_default="7", nullable=False),
    )
    op.create_check_constraint(
        "ck_blocks_cycle_days",
        "blocks",
        "cycle_days >= 1 AND cycle_days <= 14",
    )
    op.alter_column("blocks", "cycle_days", server_default=None)

    op.add_column(
        "block_placements",
        sa.Column("cycle_days", sa.Integer(), server_default="7", nullable=False),
    )
    op.create_check_constraint(
        "ck_block_placements_cycle_days",
        "block_placements",
        "cycle_days >= 1 AND cycle_days <= 14",
    )
    op.alter_column("block_placements", "cycle_days", server_default=None)

    op.drop_constraint("ck_block_schedule_day", "block_schedule_items", type_="check")
    op.create_check_constraint(
        "ck_block_schedule_day",
        "block_schedule_items",
        "day_index >= 0 AND day_index <= 13",
    )


def downgrade() -> None:
    op.drop_constraint("ck_block_schedule_day", "block_schedule_items", type_="check")
    op.create_check_constraint(
        "ck_block_schedule_day",
        "block_schedule_items",
        "day_index >= 0 AND day_index <= 6",
    )
    op.drop_constraint("ck_block_placements_cycle_days", "block_placements", type_="check")
    op.drop_column("block_placements", "cycle_days")
    op.drop_constraint("ck_blocks_cycle_days", "blocks", type_="check")
    op.drop_column("blocks", "cycle_days")
