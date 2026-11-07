"""drop inbody measurement-condition columns

Revision ID: 0015
Revises: 0014
Create Date: 2026-11-07

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015"
down_revision: str | Sequence[str] | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("ck_inbody_scans_time_of_day", "inbody_scans", type_="check")
    op.drop_column("inbody_scans", "time_of_day")
    op.drop_column("inbody_scans", "fasted")
    op.drop_column("inbody_scans", "after_workout")
    op.drop_column("inbody_scans", "dehydrated")
    op.drop_column("inbody_scans", "creatine_or_salt")


def downgrade() -> None:
    op.add_column(
        "inbody_scans",
        sa.Column("time_of_day", sa.String(length=16), nullable=False, server_default="morning"),
    )
    op.add_column(
        "inbody_scans",
        sa.Column("fasted", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column(
        "inbody_scans",
        sa.Column("after_workout", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "inbody_scans",
        sa.Column("dehydrated", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "inbody_scans",
        sa.Column("creatine_or_salt", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_check_constraint(
        "ck_inbody_scans_time_of_day",
        "inbody_scans",
        "time_of_day IN ('morning', 'afternoon', 'evening')",
    )
    op.alter_column("inbody_scans", "time_of_day", server_default=None)
    op.alter_column("inbody_scans", "fasted", server_default=None)
    op.alter_column("inbody_scans", "after_workout", server_default=None)
    op.alter_column("inbody_scans", "dehydrated", server_default=None)
    op.alter_column("inbody_scans", "creatine_or_salt", server_default=None)
