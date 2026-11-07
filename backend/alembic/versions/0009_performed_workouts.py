"""performed workouts and set logs

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-07

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009"
down_revision: str | Sequence[str] | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "performed_workouts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("planned_id", sa.Uuid(), nullable=True),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=True),
        sa.Column("note", sa.String(length=2000), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["planned_id"], ["planned_workouts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_performed_workouts_user_date", "performed_workouts", ["user_id", "date"], unique=False
    )
    op.create_index(
        "uq_performed_workouts_planned",
        "performed_workouts",
        ["planned_id"],
        unique=True,
        postgresql_where=sa.text("planned_id IS NOT NULL"),
    )
    op.create_table(
        "performed_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("performed_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("exercise_id", sa.Uuid(), nullable=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("equipment", sa.String(length=16), nullable=False),
        sa.Column("weight_type", sa.String(length=32), nullable=False),
        sa.Column("weight_unit", sa.String(length=8), nullable=False),
        sa.Column("weight_step", sa.Float(), nullable=False),
        sa.Column("note", sa.String(length=2000), nullable=True),
        sa.Column(
            "targets",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["exercise_id"], ["exercises.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["performed_id"], ["performed_workouts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("performed_id", "position", name="uq_performed_items_position"),
    )
    op.create_index("ix_performed_items_exercise", "performed_items", ["exercise_id"], unique=False)
    op.create_table(
        "set_logs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("item_id", sa.Uuid(), nullable=False),
        sa.Column("performed_id", sa.Uuid(), nullable=False),
        sa.Column("exercise_id", sa.Uuid(), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("weight", sa.Float(), nullable=True),
        sa.Column("extra_weight", sa.Float(), nullable=True),
        sa.Column("reps", sa.Integer(), nullable=True),
        sa.Column("rir", sa.Integer(), nullable=True),
        sa.Column("is_warmup", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("is_assisted", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("is_negative", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("note", sa.String(length=500), nullable=True),
        sa.CheckConstraint(
            "weight IS NULL OR (weight >= 0 AND weight <= 2000)",
            name="ck_set_logs_weight",
        ),
        sa.CheckConstraint(
            "extra_weight IS NULL OR (extra_weight >= 0 AND extra_weight <= 2000)",
            name="ck_set_logs_extra_weight",
        ),
        sa.CheckConstraint("reps IS NULL OR (reps >= 0 AND reps <= 999)", name="ck_set_logs_reps"),
        sa.CheckConstraint("rir IS NULL OR (rir >= 0 AND rir <= 5)", name="ck_set_logs_rir"),
        sa.ForeignKeyConstraint(["exercise_id"], ["exercises.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["item_id"], ["performed_items.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["performed_id"], ["performed_workouts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("item_id", "position", name="uq_set_logs_position"),
    )
    op.create_index("ix_set_logs_exercise", "set_logs", ["exercise_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_set_logs_exercise", table_name="set_logs")
    op.drop_table("set_logs")
    op.drop_index("ix_performed_items_exercise", table_name="performed_items")
    op.drop_table("performed_items")
    op.drop_index("uq_performed_workouts_planned", table_name="performed_workouts")
    op.drop_index("ix_performed_workouts_user_date", table_name="performed_workouts")
    op.drop_table("performed_workouts")
