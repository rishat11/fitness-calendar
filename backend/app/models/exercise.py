import uuid

from sqlalchemy import CheckConstraint, Float, ForeignKey, String, Uuid
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Exercise(Base):
    """Личный справочник упражнений пользователя."""

    __tablename__ = "exercises"
    __table_args__ = (
        CheckConstraint("weight_step > 0", name="ck_exercises_weight_step_positive"),
        CheckConstraint("rep_min >= 1 AND rep_min <= rep_max", name="ck_exercises_rep_range"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
    )
    name: Mapped[str] = mapped_column(String(120))
    # Значения мышечных групп — см. схемы; вторичные группы хранятся списком.
    primary_muscle: Mapped[str] = mapped_column(String(32))
    secondary_muscles: Mapped[list[str]] = mapped_column(
        ARRAY(String(32)), default=list, server_default="{}"
    )
    # Значения: barbell, dumbbell, machine, cable, bodyweight.
    equipment: Mapped[str] = mapped_column(String(16))
    # Значения: standard, per_dumbbell, stack, stack_plus_extra, bodyweight_plus,
    # bodyweight_assisted.
    weight_type: Mapped[str] = mapped_column(String(32))
    weight_unit: Mapped[str] = mapped_column(String(8), default="kg", server_default="kg")
    weight_step: Mapped[float] = mapped_column(Float)
    rep_min: Mapped[int] = mapped_column()
    rep_max: Mapped[int] = mapped_column()
