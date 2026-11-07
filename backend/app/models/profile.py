import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Profile(Base):
    """Цель, параметры тела и настройки. Одна запись на пользователя."""

    __tablename__ = "profiles"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    # Значения: muscle_gain, recomposition, cut, maintenance; NULL — цель не выбрана.
    goal: Mapped[str | None] = mapped_column(String(32), nullable=True)
    height_cm: Mapped[int | None] = mapped_column(nullable=True)
    age: Mapped[int | None] = mapped_column(nullable=True)
    # Значения: male, female; NULL — не указан.
    sex: Mapped[str | None] = mapped_column(String(16), nullable=True)
    weight_unit: Mapped[str] = mapped_column(String(8), default="kg", server_default="kg")
    # Значения: light, dark, system.
    theme: Mapped[str] = mapped_column(String(8), default="system", server_default="system")
    # Когда пользователь в последний раз скачал полный JSON. Нужно для напоминания раз в месяц.
    last_exported_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
