import uuid
from decimal import Decimal

from sqlalchemy import CheckConstraint, ForeignKey, Numeric, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class NutritionIntake(Base):
    """Текущий уровень потребления БЖУ. Одна запись на пользователя.

    Калории в таблице нет: их считает сервис из граммов (Б×4 + У×4 + Ж×9).
    """

    __tablename__ = "nutrition_intake"
    __table_args__ = (
        CheckConstraint(
            "protein_g >= 0 AND protein_g <= 2000",
            name="ck_nutrition_intake_protein",
        ),
        CheckConstraint("fat_g >= 0 AND fat_g <= 2000", name="ck_nutrition_intake_fat"),
        CheckConstraint("carbs_g >= 0 AND carbs_g <= 2000", name="ck_nutrition_intake_carbs"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    protein_g: Mapped[Decimal] = mapped_column(Numeric(6, 1))
    fat_g: Mapped[Decimal] = mapped_column(Numeric(6, 1))
    carbs_g: Mapped[Decimal] = mapped_column(Numeric(6, 1))
