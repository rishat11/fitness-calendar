import uuid
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

WEEK_TYPES = ("high_reps", "hypertrophy", "strength", "deload", "free")
MAX_BLOCK_WEEKS = 12
# Длина одного цикла в днях. 7 — календарная неделя, меньше — сплит короче недели.
MAX_CYCLE_DAYS = 14


class Block(Base):
    """Свой блок периодизации (библиотека): название, циклы и расписание цикла.

    Цикл — это не обязательно календарная неделя: его длина задаётся в днях.
    Блок сам по себе не стоит в календаре. Применение создаёт `BlockPlacement` с датой старта.
    """

    __tablename__ = "blocks"
    __table_args__ = (
        CheckConstraint(
            f"length_weeks >= 1 AND length_weeks <= {MAX_BLOCK_WEEKS}",
            name="ck_blocks_length",
        ),
        CheckConstraint(
            f"cycle_days >= 1 AND cycle_days <= {MAX_CYCLE_DAYS}",
            name="ck_blocks_cycle_days",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
    )
    name: Mapped[str] = mapped_column(String(120))
    length_weeks: Mapped[int] = mapped_column(Integer)
    cycle_days: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    weeks: Mapped[list["BlockWeek"]] = relationship(
        back_populates="block",
        order_by="BlockWeek.position",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    schedule: Mapped[list["BlockScheduleItem"]] = relationship(
        back_populates="block",
        order_by="BlockScheduleItem.day_index",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class BlockWeek(Base):
    """Один цикл блока: тип и параметры, которые накладываются на тренировки расписания."""

    __tablename__ = "block_weeks"
    __table_args__ = (
        UniqueConstraint("block_id", "position", name="uq_block_weeks_position"),
        CheckConstraint(
            "week_type IN ('high_reps', 'hypertrophy', 'strength', 'deload', 'free')",
            name="ck_block_weeks_type",
        ),
        CheckConstraint(
            "rep_min >= 1 AND rep_min <= rep_max AND rep_max <= 30", name="ck_block_weeks_reps"
        ),
        CheckConstraint("target_rir >= 0 AND target_rir <= 5", name="ck_block_weeks_rir"),
        CheckConstraint(
            "volume_multiplier > 0 AND volume_multiplier <= 1",
            name="ck_block_weeks_volume",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    block_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("blocks.id", ondelete="CASCADE"),
        index=True,
    )
    # Порядковый номер в блоке, с 1.
    position: Mapped[int] = mapped_column(Integer)
    week_type: Mapped[str] = mapped_column(String(16))
    rep_min: Mapped[int] = mapped_column(Integer)
    rep_max: Mapped[int] = mapped_column(Integer)
    target_rir: Mapped[int] = mapped_column(Integer)
    # Доля подходов от базового шаблона, от 0 до 1.
    volume_multiplier: Mapped[float] = mapped_column(Float)

    block: Mapped[Block] = relationship(back_populates="weeks")


class BlockScheduleItem(Base):
    """День цикла: тренировка (снимок шаблона) или отдых. Дни без записи свободны."""

    __tablename__ = "block_schedule_items"
    __table_args__ = (
        UniqueConstraint("block_id", "day_index", name="uq_block_schedule_day"),
        CheckConstraint(
            f"day_index >= 0 AND day_index <= {MAX_CYCLE_DAYS - 1}",
            name="ck_block_schedule_day",
        ),
        CheckConstraint("kind IN ('workout', 'rest')", name="ck_block_schedule_kind"),
        CheckConstraint(
            "(kind = 'rest') = (name IS NULL)",
            name="ck_block_schedule_name",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    block_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("blocks.id", ondelete="CASCADE"),
        index=True,
    )
    # День от начала цикла: 0 — первый день.
    day_index: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(8))
    name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    # Ссылка только для справки: удаление шаблона не меняет блок.
    template_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("workout_templates.id", ondelete="SET NULL"),
        nullable=True,
    )
    # Позиции тренировки на момент сохранения блока (как в плане), правка шаблона блок не меняет.
    snapshot: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)

    block: Mapped[Block] = relationship(back_populates="schedule")


class BlockPlacement(Base):
    """Блок, применённый к календарю с датой старта.

    Строки плана на каждый день не создаются: даты вычисляются от `start_date`.
    Строка появляется только у тренировки, которую отметили, перенесли или сдвинули.
    Сдвиг блока целиком меняет `start_date`; `end_date` — граница блока, она едет с
    тренировками (см. правило в `app.services.plan_shift`). `repeats` без `end_date`
    продолжает те же циклы по кругу, пока размещение не уберут.
    Недели и расписание хранятся снимком, поэтому правка библиотеки блок не меняет.
    """

    __tablename__ = "block_placements"
    __table_args__ = (
        CheckConstraint(
            "(repeats = false AND end_date IS NOT NULL AND end_date >= start_date) "
            "OR (repeats = true AND end_date IS NULL)",
            name="ck_block_placements_dates",
        ),
        CheckConstraint(
            f"length_weeks >= 1 AND length_weeks <= {MAX_BLOCK_WEEKS}",
            name="ck_block_placements_length",
        ),
        CheckConstraint(
            f"cycle_days >= 1 AND cycle_days <= {MAX_CYCLE_DAYS}",
            name="ck_block_placements_cycle_days",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
    )
    # Ссылка только для справки: удаление блока из библиотеки не снимает его с календаря.
    block_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("blocks.id", ondelete="SET NULL"),
        nullable=True,
    )
    name: Mapped[str] = mapped_column(String(120))
    length_weeks: Mapped[int] = mapped_column(Integer)
    cycle_days: Mapped[int] = mapped_column(Integer)
    repeats: Mapped[bool] = mapped_column(Boolean, default=False)
    # Календарные даты без часового пояса. У повтора без конца `end_date` пустой.
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    weeks_snapshot: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    schedule_snapshot: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
