"""periodization: blocks, weeks, schedule and placements on the calendar

Revision ID: 0012
Revises: 0011
Create Date: 2026-11-07

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0012"
down_revision: str | Sequence[str] | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _created_at() -> sa.Column:
    return sa.Column(
        "created_at",
        sa.DateTime(timezone=True),
        server_default=sa.func.now(),
        nullable=False,
    )


def upgrade() -> None:
    op.create_table(
        "blocks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("length_weeks", sa.Integer(), nullable=False),
        _created_at(),
        sa.CheckConstraint("length_weeks >= 1 AND length_weeks <= 12", name="ck_blocks_length"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_blocks_user_id"), "blocks", ["user_id"], unique=False)

    op.create_table(
        "block_weeks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("block_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("week_type", sa.String(length=16), nullable=False),
        sa.Column("rep_min", sa.Integer(), nullable=False),
        sa.Column("rep_max", sa.Integer(), nullable=False),
        sa.Column("target_rir", sa.Integer(), nullable=False),
        sa.Column("volume_multiplier", sa.Float(), nullable=False),
        sa.CheckConstraint(
            "week_type IN ('high_reps', 'hypertrophy', 'strength', 'deload', 'free')",
            name="ck_block_weeks_type",
        ),
        sa.CheckConstraint(
            "rep_min >= 1 AND rep_min <= rep_max AND rep_max <= 30",
            name="ck_block_weeks_reps",
        ),
        sa.CheckConstraint("target_rir >= 0 AND target_rir <= 5", name="ck_block_weeks_rir"),
        sa.CheckConstraint(
            "volume_multiplier > 0 AND volume_multiplier <= 1",
            name="ck_block_weeks_volume",
        ),
        sa.ForeignKeyConstraint(["block_id"], ["blocks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("block_id", "position", name="uq_block_weeks_position"),
    )
    op.create_index(op.f("ix_block_weeks_block_id"), "block_weeks", ["block_id"], unique=False)

    op.create_table(
        "block_schedule_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("block_id", sa.Uuid(), nullable=False),
        sa.Column("day_index", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=8), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=True),
        sa.Column("template_id", sa.Uuid(), nullable=True),
        sa.Column("snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.CheckConstraint("day_index >= 0 AND day_index <= 6", name="ck_block_schedule_day"),
        sa.CheckConstraint("kind IN ('workout', 'rest')", name="ck_block_schedule_kind"),
        sa.CheckConstraint("(kind = 'rest') = (name IS NULL)", name="ck_block_schedule_name"),
        sa.ForeignKeyConstraint(["block_id"], ["blocks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["template_id"], ["workout_templates.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("block_id", "day_index", name="uq_block_schedule_day"),
    )
    op.create_index(
        op.f("ix_block_schedule_items_block_id"),
        "block_schedule_items",
        ["block_id"],
        unique=False,
    )

    op.create_table(
        "block_placements",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("block_id", sa.Uuid(), nullable=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("length_weeks", sa.Integer(), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("weeks_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("schedule_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        _created_at(),
        sa.CheckConstraint("end_date >= start_date", name="ck_block_placements_dates"),
        sa.CheckConstraint(
            "length_weeks >= 1 AND length_weeks <= 12",
            name="ck_block_placements_length",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["block_id"], ["blocks.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_block_placements_user_id"),
        "block_placements",
        ["user_id"],
        unique=False,
    )

    op.add_column("planned_workouts", sa.Column("placement_id", sa.Uuid(), nullable=True))
    op.add_column("planned_workouts", sa.Column("day_offset", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_planned_workouts_placement_id",
        "planned_workouts",
        "block_placements",
        ["placement_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_check_constraint(
        "ck_planned_workouts_placement",
        "planned_workouts",
        "(placement_id IS NULL) = (day_offset IS NULL)",
    )
    op.create_index(
        "uq_planned_workouts_placement_offset",
        "planned_workouts",
        ["placement_id", "day_offset"],
        unique=True,
        postgresql_where=sa.text("placement_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_planned_workouts_placement_offset", table_name="planned_workouts")
    op.drop_constraint("ck_planned_workouts_placement", "planned_workouts", type_="check")
    op.drop_constraint("fk_planned_workouts_placement_id", "planned_workouts", type_="foreignkey")
    op.drop_column("planned_workouts", "day_offset")
    op.drop_column("planned_workouts", "placement_id")

    op.drop_index(op.f("ix_block_placements_user_id"), table_name="block_placements")
    op.drop_table("block_placements")
    op.drop_index(op.f("ix_block_schedule_items_block_id"), table_name="block_schedule_items")
    op.drop_table("block_schedule_items")
    op.drop_index(op.f("ix_block_weeks_block_id"), table_name="block_weeks")
    op.drop_table("block_weeks")
    op.drop_index(op.f("ix_blocks_user_id"), table_name="blocks")
    op.drop_table("blocks")
