"""exercises: personal reference of exercises per user

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-06

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: str | Sequence[str] | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "exercises",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("primary_muscle", sa.String(length=32), nullable=False),
        sa.Column(
            "secondary_muscles",
            postgresql.ARRAY(sa.String(length=32)),
            server_default="{}",
            nullable=False,
        ),
        sa.Column("equipment", sa.String(length=16), nullable=False),
        sa.Column("weight_type", sa.String(length=32), nullable=False),
        sa.Column("weight_unit", sa.String(length=8), server_default="kg", nullable=False),
        sa.Column("weight_step", sa.Float(), nullable=False),
        sa.Column("rep_min", sa.Integer(), nullable=False),
        sa.Column("rep_max", sa.Integer(), nullable=False),
        sa.Column("archived", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.CheckConstraint("weight_step > 0", name="ck_exercises_weight_step_positive"),
        sa.CheckConstraint("rep_min >= 1 AND rep_min <= rep_max", name="ck_exercises_rep_range"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_exercises_user_id"), "exercises", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_exercises_user_id"), table_name="exercises")
    op.drop_table("exercises")
