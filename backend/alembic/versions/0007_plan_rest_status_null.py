"""planned_workouts: rest days have no status

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-07

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | Sequence[str] | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "planned_workouts",
        "status",
        existing_type=sa.String(length=16),
        nullable=True,
        server_default=None,
    )
    op.execute("UPDATE planned_workouts SET status = NULL WHERE kind = 'rest'")
    op.drop_constraint("ck_planned_workouts_status", "planned_workouts", type_="check")
    op.create_check_constraint(
        "ck_planned_workouts_status",
        "planned_workouts",
        "status IS NULL OR status IN ('planned', 'done', 'skipped', 'moved')",
    )
    op.create_check_constraint(
        "ck_planned_workouts_status_kind",
        "planned_workouts",
        "(kind = 'rest') = (status IS NULL)",
    )


def downgrade() -> None:
    op.drop_constraint("ck_planned_workouts_status_kind", "planned_workouts", type_="check")
    op.drop_constraint("ck_planned_workouts_status", "planned_workouts", type_="check")
    op.execute("UPDATE planned_workouts SET status = 'planned' WHERE status IS NULL")
    op.create_check_constraint(
        "ck_planned_workouts_status",
        "planned_workouts",
        "status IN ('planned', 'done', 'skipped', 'moved')",
    )
    op.alter_column(
        "planned_workouts",
        "status",
        existing_type=sa.String(length=16),
        nullable=False,
        server_default="planned",
    )
