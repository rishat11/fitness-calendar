import uuid
from datetime import UTC, date, datetime, time
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    Time,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class InbodyScan(Base):
    """Один ручной замер InBody. Правка не пересчитывает прошлые рекомендации: их нет в базе.

    Сегменты — необязательный JSON. Оценку прибора, ИМТ и норму калорий с листа не храним.
    """

    __tablename__ = "inbody_scans"
    __table_args__ = (
        CheckConstraint(
            "weight_kg >= 20 AND weight_kg <= 400",
            name="ck_inbody_scans_weight",
        ),
        CheckConstraint("smm_kg >= 0 AND smm_kg <= 200", name="ck_inbody_scans_smm"),
        CheckConstraint("bfm_kg >= 0 AND bfm_kg <= 300", name="ck_inbody_scans_bfm"),
        CheckConstraint(
            "pbf_percent >= 0.1 AND pbf_percent <= 80",
            name="ck_inbody_scans_pbf",
        ),
        CheckConstraint("tbw_l >= 1 AND tbw_l <= 200", name="ck_inbody_scans_tbw"),
        CheckConstraint(
            "visceral_fat_level >= 1 AND visceral_fat_level <= 30",
            name="ck_inbody_scans_visceral",
        ),
        CheckConstraint("bmr_kcal >= 500 AND bmr_kcal <= 6000", name="ck_inbody_scans_bmr"),
        Index("ix_inbody_scans_user_measured_on", "user_id", "measured_on"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="CASCADE"),
    )
    measured_on: Mapped[date] = mapped_column(Date)
    measured_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    weight_kg: Mapped[Decimal] = mapped_column(Numeric(5, 1))
    smm_kg: Mapped[Decimal] = mapped_column(Numeric(5, 1))
    bfm_kg: Mapped[Decimal] = mapped_column(Numeric(5, 1))
    pbf_percent: Mapped[Decimal] = mapped_column(Numeric(4, 1))
    tbw_l: Mapped[Decimal] = mapped_column(Numeric(5, 1))
    visceral_fat_level: Mapped[int] = mapped_column(Integer)
    bmr_kcal: Mapped[int] = mapped_column(Integer)
    segments: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        default=lambda: datetime.now(UTC),
    )
