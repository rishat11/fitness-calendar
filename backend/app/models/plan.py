import uuid
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    String,
    Uuid,
    false,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

KIND_WORKOUT = "workout"
KIND_REST = "rest"
STATUS_PLANNED = "planned"
STATUS_DONE = "done"
STATUS_SKIPPED = "skipped"
STATUS_MOVED = "moved"


class PlannedWorkout(Base):
    """Запись плана на дату: тренировка или день отдыха.

    Тренировка хранит снимок структуры шаблона в `snapshot`, поэтому правка шаблона
    план не меняет. Отдых не содержит ни снимка, ни статуса.
    """

    __tablename__ = "planned_workouts"
    __table_args__ = (
        CheckConstraint("kind IN ('workout', 'rest')", name="ck_planned_workouts_kind"),
        CheckConstraint(
            "status IS NULL OR status IN ('planned', 'done', 'skipped', 'moved')",
            name="ck_planned_workouts_status",
        ),
        # У тренировки статус обязателен, у дня отдыха его нет.
        CheckConstraint(
            "(kind = 'rest') = (status IS NULL)",
            name="ck_planned_workouts_status_kind",
        ),
        CheckConstraint("kind = 'rest' OR name IS NOT NULL", name="ck_planned_workouts_name"),
        Index("ix_planned_workouts_user_date", "user_id", "date"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="CASCADE"),
    )
    # Календарная дата без часового пояса.
    date: Mapped[date] = mapped_column(Date)
    kind: Mapped[str] = mapped_column(String(8))
    # Ссылка на шаблон только для справки: удаление шаблона план не трогает.
    template_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("workout_templates.id", ondelete="SET NULL"),
        nullable=True,
    )
    name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    # Список позиций: exercise (снимок упражнения) и sets (подходы), см. схемы плана.
    snapshot: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list, server_default="[]")
    # NULL только у дня отдыха; у тренировки задаётся явно при создании.
    status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    is_fixed: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    position: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    @property
    def items(self) -> list[dict[str, Any]]:
        """Имя поля для ответа API: позиции снимка."""
        return self.snapshot


class PlanChangeLog(Base):
    """Одна операция сдвига плана. Хранит прежние даты, чтобы отменить её целиком.

    `seq` монотонно растёт и задаёт порядок отмены, даже если несколько записей
    попали в одну транзакцию. На пользователя оставляем только последние операции.
    """

    __tablename__ = "plan_change_logs"
    __table_args__ = (
        CheckConstraint(
            "operation IN ('shift_following', 'shift_only', 'skip', 'swap')",
            name="ck_plan_change_logs_operation",
        ),
        Index("ix_plan_change_logs_user_seq", "user_id", "seq"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    seq: Mapped[int] = mapped_column(BigInteger, Identity(always=True), unique=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="CASCADE"),
    )
    operation: Mapped[str] = mapped_column(String(32))
    # changes: id, прежние date, status и position. Этого достаточно, чтобы вернуть план.
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("clock_timestamp()"),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
