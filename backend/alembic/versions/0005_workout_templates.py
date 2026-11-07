"""workout_templates: library of workouts with exercises and per-set targets

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-06

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | Sequence[str] | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "workout_templates",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_workout_templates_user_id"), "workout_templates", ["user_id"])

    op.create_table(
        "workout_template_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("template_id", sa.Uuid(), nullable=False),
        sa.Column("exercise_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["template_id"], ["workout_templates.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["exercise_id"], ["exercises.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_workout_template_items_template_id"),
        "workout_template_items",
        ["template_id"],
    )
    op.create_index(
        op.f("ix_workout_template_items_exercise_id"),
        "workout_template_items",
        ["exercise_id"],
    )

    op.create_table(
        "workout_template_sets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("item_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("rep_min", sa.Integer(), nullable=False),
        sa.Column("rep_max", sa.Integer(), nullable=False),
        sa.Column("target_rir", sa.Integer(), nullable=True),
        sa.Column("rest_seconds", sa.Integer(), nullable=True),
        sa.CheckConstraint("rep_min >= 1 AND rep_min <= rep_max", name="ck_workout_sets_rep_range"),
        sa.CheckConstraint(
            "target_rir IS NULL OR (target_rir >= 0 AND target_rir <= 5)",
            name="ck_workout_sets_rir",
        ),
        sa.CheckConstraint(
            "rest_seconds IS NULL OR (rest_seconds >= 0 AND rest_seconds <= 1800)",
            name="ck_workout_sets_rest",
        ),
        sa.ForeignKeyConstraint(["item_id"], ["workout_template_items.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_workout_template_sets_item_id"), "workout_template_sets", ["item_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_workout_template_sets_item_id"), table_name="workout_template_sets")
    op.drop_table("workout_template_sets")
    op.drop_index(
        op.f("ix_workout_template_items_exercise_id"), table_name="workout_template_items"
    )
    op.drop_index(
        op.f("ix_workout_template_items_template_id"), table_name="workout_template_items"
    )
    op.drop_table("workout_template_items")
    op.drop_index(op.f("ix_workout_templates_user_id"), table_name="workout_templates")
    op.drop_table("workout_templates")
