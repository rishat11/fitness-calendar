import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class ProgressionDecision(Base):
    """Принятая или отклонённая подсказка.

    Отпечаток — статус, id последней сессии и предлагаемый вес. Пока расчёт
    даёт тот же отпечаток, решение скрывает подсказку. Новая тренировка меняет
    отпечаток, и подсказка показывается снова. Шаблон и план здесь не хранятся.
    """

    __tablename__ = "progression_decisions"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "exercise_id",
            "fingerprint",
            name="uq_progression_decisions_fingerprint",
        ),
        CheckConstraint(
            "action IN ('accept', 'reject')",
            name="ck_progression_decisions_action",
        ),
        CheckConstraint(
            "status IN ('increase_weight', 'continue', 'stagnation')",
            name="ck_progression_decisions_status",
        ),
        Index("ix_progression_decisions_user_exercise", "user_id", "exercise_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="CASCADE"),
    )
    exercise_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("exercises.id", ondelete="CASCADE"),
    )
    status: Mapped[str] = mapped_column(String(32))
    last_session_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("performed_workouts.id", ondelete="CASCADE"),
    )
    suggested_weight: Mapped[float | None] = mapped_column(Float, nullable=True)
    fingerprint: Mapped[str] = mapped_column(String(96))
    action: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("clock_timestamp()"),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
