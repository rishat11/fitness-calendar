"""current nutrition intake: one macro row per user, calories are not stored

Revision ID: 0013
Revises: 0012
Create Date: 2026-11-07

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: str | Sequence[str] | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "nutrition_intake",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("protein_g", sa.Numeric(precision=6, scale=1), nullable=False),
        sa.Column("fat_g", sa.Numeric(precision=6, scale=1), nullable=False),
        sa.Column("carbs_g", sa.Numeric(precision=6, scale=1), nullable=False),
        sa.CheckConstraint(
            "protein_g >= 0 AND protein_g <= 2000",
            name="ck_nutrition_intake_protein",
        ),
        sa.CheckConstraint("fat_g >= 0 AND fat_g <= 2000", name="ck_nutrition_intake_fat"),
        sa.CheckConstraint("carbs_g >= 0 AND carbs_g <= 2000", name="ck_nutrition_intake_carbs"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
    )


def downgrade() -> None:
    op.drop_table("nutrition_intake")
