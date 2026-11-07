"""profiles: goal, body parameters, units and theme

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-06

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | Sequence[str] | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "profiles",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("goal", sa.String(length=32), nullable=True),
        sa.Column("height_cm", sa.Integer(), nullable=True),
        sa.Column("age", sa.Integer(), nullable=True),
        sa.Column("sex", sa.String(length=16), nullable=True),
        sa.Column("weight_unit", sa.String(length=8), server_default="kg", nullable=False),
        sa.Column("theme", sa.String(length=8), server_default="system", nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
    )
    # Существующим аккаунтам сразу создаём профиль с настройками по умолчанию.
    op.execute("INSERT INTO profiles (user_id) SELECT id FROM users")


def downgrade() -> None:
    op.drop_table("profiles")
