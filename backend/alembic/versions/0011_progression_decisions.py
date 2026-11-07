"""progression decisions: accept or reject a double-progression hint

Revision ID: 0011
Revises: 0010
Create Date: 2026-11-07

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: str | Sequence[str] | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "progression_decisions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("exercise_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("last_session_id", sa.Uuid(), nullable=False),
        sa.Column("suggested_weight", sa.Float(), nullable=True),
        sa.Column("fingerprint", sa.String(length=96), nullable=False),
        sa.Column("action", sa.String(length=16), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "action IN ('accept', 'reject')",
            name="ck_progression_decisions_action",
        ),
        sa.CheckConstraint(
            "status IN ('increase_weight', 'continue', 'stagnation')",
            name="ck_progression_decisions_status",
        ),
        sa.ForeignKeyConstraint(["exercise_id"], ["exercises.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["last_session_id"], ["performed_workouts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "exercise_id",
            "fingerprint",
            name="uq_progression_decisions_fingerprint",
        ),
    )
    op.create_index(
        "ix_progression_decisions_user_exercise",
        "progression_decisions",
        ["user_id", "exercise_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_progression_decisions_user_exercise", table_name="progression_decisions")
    op.drop_table("progression_decisions")
