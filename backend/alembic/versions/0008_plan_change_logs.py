"""plan_change_logs: history of plan shifts for one-step undo

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-07

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008"
down_revision: str | Sequence[str] | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "plan_change_logs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "seq",
            sa.BigInteger(),
            sa.Identity(always=True, start=1, increment=1),
            nullable=False,
        ),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("operation", sa.String(length=32), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "operation IN ('shift_following', 'shift_only', 'skip', 'swap')",
            name="ck_plan_change_logs_operation",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("seq", name="uq_plan_change_logs_seq"),
    )
    op.create_index(
        "ix_plan_change_logs_user_seq", "plan_change_logs", ["user_id", "seq"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_plan_change_logs_user_seq", table_name="plan_change_logs")
    op.drop_table("plan_change_logs")
