"""inbody scans: manual body-composition measurements per user

Revision ID: 0014
Revises: 0013
Create Date: 2026-11-07

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0014"
down_revision: str | Sequence[str] | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "inbody_scans",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("measured_on", sa.Date(), nullable=False),
        sa.Column("measured_time", sa.Time(), nullable=True),
        sa.Column("weight_kg", sa.Numeric(precision=5, scale=1), nullable=False),
        sa.Column("smm_kg", sa.Numeric(precision=5, scale=1), nullable=False),
        sa.Column("bfm_kg", sa.Numeric(precision=5, scale=1), nullable=False),
        sa.Column("pbf_percent", sa.Numeric(precision=4, scale=1), nullable=False),
        sa.Column("tbw_l", sa.Numeric(precision=5, scale=1), nullable=False),
        sa.Column("visceral_fat_level", sa.Integer(), nullable=False),
        sa.Column("bmr_kcal", sa.Integer(), nullable=False),
        sa.Column("segments", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("time_of_day", sa.String(length=16), nullable=False),
        sa.Column("fasted", sa.Boolean(), nullable=False),
        sa.Column("after_workout", sa.Boolean(), nullable=False),
        sa.Column("dehydrated", sa.Boolean(), nullable=False),
        sa.Column("creatine_or_salt", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "weight_kg >= 20 AND weight_kg <= 400",
            name="ck_inbody_scans_weight",
        ),
        sa.CheckConstraint("smm_kg >= 0 AND smm_kg <= 200", name="ck_inbody_scans_smm"),
        sa.CheckConstraint("bfm_kg >= 0 AND bfm_kg <= 300", name="ck_inbody_scans_bfm"),
        sa.CheckConstraint(
            "pbf_percent >= 0.1 AND pbf_percent <= 80",
            name="ck_inbody_scans_pbf",
        ),
        sa.CheckConstraint("tbw_l >= 1 AND tbw_l <= 200", name="ck_inbody_scans_tbw"),
        sa.CheckConstraint(
            "visceral_fat_level >= 1 AND visceral_fat_level <= 30",
            name="ck_inbody_scans_visceral",
        ),
        sa.CheckConstraint("bmr_kcal >= 500 AND bmr_kcal <= 6000", name="ck_inbody_scans_bmr"),
        sa.CheckConstraint(
            "time_of_day IN ('morning', 'afternoon', 'evening')",
            name="ck_inbody_scans_time_of_day",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_inbody_scans_user_measured_on",
        "inbody_scans",
        ["user_id", "measured_on"],
    )


def downgrade() -> None:
    op.drop_index("ix_inbody_scans_user_measured_on", table_name="inbody_scans")
    op.drop_table("inbody_scans")
