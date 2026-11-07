import uuid
from datetime import UTC, date, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    Uuid,
    false,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class PerformedWorkout(Base):
    """Факт тренировки. Правка плана и шаблона его не меняет.

    При завершении плановая тренировка, если она ещё запланирована, отмечается выполненной.
    """

    __tablename__ = "performed_workouts"
    __table_args__ = (
        Index("ix_performed_workouts_user_date", "user_id", "date"),
        # Одна запись факта на запланированную тренировку: повторный старт её продолжает.
        Index(
            "uq_performed_workouts_planned",
            "planned_id",
            unique=True,
            postgresql_where="planned_id IS NOT NULL",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="CASCADE"),
    )
    # Удаление записи плана факт не стирает: шаблон, план и факт раздельно.
    planned_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("planned_workouts.id", ondelete="SET NULL"),
        nullable=True,
    )
    date: Mapped[date] = mapped_column(Date)
    name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    note: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    items: Mapped[list["PerformedItem"]] = relationship(
        back_populates="workout",
        order_by="PerformedItem.position",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class PerformedItem(Base):
    """Упражнение внутри факта. Снимок учёта веса нужен, даже если справочник потом изменится."""

    __tablename__ = "performed_items"
    __table_args__ = (
        UniqueConstraint("performed_id", "position", name="uq_performed_items_position"),
        Index("ix_performed_items_exercise", "exercise_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    performed_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("performed_workouts.id", ondelete="CASCADE"),
    )
    position: Mapped[int] = mapped_column()
    # NULL, если упражнение удалили из справочника: название остаётся в снимке.
    exercise_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("exercises.id", ondelete="SET NULL"),
        nullable=True,
    )
    name: Mapped[str] = mapped_column(String(120))
    equipment: Mapped[str] = mapped_column(String(16))
    weight_type: Mapped[str] = mapped_column(String(32))
    weight_unit: Mapped[str] = mapped_column(String(8))
    weight_step: Mapped[float] = mapped_column(Float)
    note: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    # Цели подходов из плана на момент старта. После замены упражнения очищаются.
    targets: Mapped[list[dict[str, int | None]]] = mapped_column(
        JSONB, default=list, server_default="[]"
    )

    workout: Mapped[PerformedWorkout] = relationship(back_populates="items")
    sets: Mapped[list["SetLog"]] = relationship(
        back_populates="item",
        order_by="SetLog.position",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class SetLog(Base):
    """Один подход. Клиент может задать id, чтобы повтор при обрыве сети не создал дубль."""

    __tablename__ = "set_logs"
    __table_args__ = (
        UniqueConstraint("item_id", "position", name="uq_set_logs_position"),
        CheckConstraint(
            "weight IS NULL OR (weight >= 0 AND weight <= 2000)",
            name="ck_set_logs_weight",
        ),
        CheckConstraint(
            "extra_weight IS NULL OR (extra_weight >= 0 AND extra_weight <= 2000)",
            name="ck_set_logs_extra_weight",
        ),
        CheckConstraint("reps IS NULL OR (reps >= 0 AND reps <= 999)", name="ck_set_logs_reps"),
        CheckConstraint("rir IS NULL OR (rir >= 0 AND rir <= 5)", name="ck_set_logs_rir"),
        Index("ix_set_logs_exercise", "exercise_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    item_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("performed_items.id", ondelete="CASCADE"),
    )
    performed_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("performed_workouts.id", ondelete="CASCADE"),
    )
    exercise_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("exercises.id", ondelete="SET NULL"),
        nullable=True,
    )
    position: Mapped[int] = mapped_column()
    weight: Mapped[float | None] = mapped_column(Float, nullable=True)
    extra_weight: Mapped[float | None] = mapped_column(Float, nullable=True)
    reps: Mapped[int | None] = mapped_column(nullable=True)
    # 0–4 и 5 как «4+», как и целевой RIR в шаблоне.
    rir: Mapped[int | None] = mapped_column(nullable=True)
    is_warmup: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    is_assisted: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    is_negative: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)

    item: Mapped[PerformedItem] = relationship(back_populates="sets")
