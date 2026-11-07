import uuid
from datetime import UTC, datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.exercise import Exercise


class WorkoutTemplate(Base):
    """Тренировка из библиотеки пользователя: произвольный список упражнений."""

    __tablename__ = "workout_templates"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
    )
    name: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    items: Mapped[list["WorkoutTemplateItem"]] = relationship(
        back_populates="template",
        order_by="WorkoutTemplateItem.position",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class WorkoutTemplateItem(Base):
    """Позиция тренировки: упражнение и его подходы."""

    __tablename__ = "workout_template_items"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    template_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("workout_templates.id", ondelete="CASCADE"),
        index=True,
    )
    # RESTRICT: упражнение, входящее в тренировку, не удаляется молча (см. сервис упражнений).
    exercise_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("exercises.id", ondelete="RESTRICT"),
        index=True,
    )
    position: Mapped[int] = mapped_column()

    template: Mapped[WorkoutTemplate] = relationship(back_populates="items")
    exercise: Mapped[Exercise] = relationship(lazy="selectin")
    sets: Mapped[list["WorkoutTemplateSet"]] = relationship(
        back_populates="item",
        order_by="WorkoutTemplateSet.position",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class WorkoutTemplateSet(Base):
    """Один подход в позиции. Подходы одного упражнения могут различаться."""

    __tablename__ = "workout_template_sets"
    __table_args__ = (
        CheckConstraint("rep_min >= 1 AND rep_min <= rep_max", name="ck_workout_sets_rep_range"),
        CheckConstraint(
            "target_rir IS NULL OR (target_rir >= 0 AND target_rir <= 5)",
            name="ck_workout_sets_rir",
        ),
        CheckConstraint(
            "rest_seconds IS NULL OR (rest_seconds >= 0 AND rest_seconds <= 1800)",
            name="ck_workout_sets_rest",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    item_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("workout_template_items.id", ondelete="CASCADE"),
        index=True,
    )
    position: Mapped[int] = mapped_column()
    rep_min: Mapped[int] = mapped_column()
    rep_max: Mapped[int] = mapped_column()
    target_rir: Mapped[int | None] = mapped_column(nullable=True)
    rest_seconds: Mapped[int | None] = mapped_column(nullable=True)

    item: Mapped[WorkoutTemplateItem] = relationship(back_populates="sets")
