"""planned_workouts: calendar entries (workouts with template snapshot, rest days)

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-06

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006"
down_revision: str | Sequence[str] | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "planned_workouts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("kind", sa.String(length=8), nullable=False),
        sa.Column("template_id", sa.Uuid(), nullable=True),
        sa.Column("name", sa.String(length=120), nullable=True),
        sa.Column(
            "snapshot",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
        sa.Column("status", sa.String(length=16), server_default="planned", nullable=False),
        sa.Column("is_fixed", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("kind IN ('workout', 'rest')", name="ck_planned_workouts_kind"),
        sa.CheckConstraint(
            "status IN ('planned', 'done', 'skipped', 'moved')",
            name="ck_planned_workouts_status",
        ),
        sa.CheckConstraint("kind = 'rest' OR name IS NOT NULL", name="ck_planned_workouts_name"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["template_id"], ["workout_templates.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_planned_workouts_user_date", "planned_workouts", ["user_id", "date"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_planned_workouts_user_date", table_name="planned_workouts")
    op.drop_table("planned_workouts")
