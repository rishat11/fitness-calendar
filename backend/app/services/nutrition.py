"""Текущее БЖУ и расчёт цели по правилу spec.md 4.10.

Калории текущего потребления не хранятся: их считает macro_calories.
target_macros из API загрузки замера не вызывается: замера InBody ещё нет.
На этапе 4 после успешного сохранения замера нужно вызвать target_macros
и отдать эти граммы и калории вместо заглушки unavailable_macro_target.
"""

import uuid
from dataclasses import dataclass
from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.nutrition import NutritionIntake

GoalName = Literal["muscle_gain", "recomposition", "cut", "maintenance"]
Number = Decimal | int | float

# Точки внутри диапазона 1,6–2,2 г на кг массы тела.
PROTEIN_G_PER_KG: dict[GoalName, Decimal] = {
    "muscle_gain": Decimal("1.8"),
    "recomposition": Decimal("2.0"),
    "cut": Decimal("2.2"),
    "maintenance": Decimal("1.6"),
}
# Точки внутри 0,8–1 г/кг. Набор и сушка ближе к нижней границе: остаток уходит в углеводы.
FAT_G_PER_KG: dict[GoalName, Decimal] = {
    "muscle_gain": Decimal("0.8"),
    "recomposition": Decimal("0.9"),
    "cut": Decimal("0.8"),
    "maintenance": Decimal("1.0"),
}
# Шаг из 4.10: профицит или дефицит 250 ккал от оценки поддержания.
GOAL_KCAL_DELTA: dict[GoalName, int] = {
    "muscle_gain": 250,
    "recomposition": 0,
    "cut": -250,
    "maintenance": 0,
}

# Кэтча–МакАрдла: нет роста, возраста и пола, зато есть процент жира из InBody.
KATCH_INTERCEPT = Decimal("370")
KATCH_PER_KG_LBM = Decimal("21.6")
# В профиле нет уровня активности. 1,5 — умеренная активность человека, который тренируется.
TRAINING_ACTIVITY = Decimal("1.5")
FAT_CALORIE_SHARE = Decimal("0.20")

NO_INBODY_SCAN_REASON = "нет замера InBody"

_GRAM = Decimal("0.1")
_KCAL = Decimal("1")


@dataclass(frozen=True)
class IntakeView:
    protein_g: Decimal | None
    fat_g: Decimal | None
    carbs_g: Decimal | None
    calories: Decimal | None


@dataclass(frozen=True)
class MacroTarget:
    """Граммы и калории на день. Пустой результат — все поля None, граммы не выдуманы."""

    protein_g: Decimal | None = None
    fat_g: Decimal | None = None
    carbs_g: Decimal | None = None
    calories: int | None = None

    def is_empty(self) -> bool:
        return (
            self.protein_g is None
            and self.fat_g is None
            and self.carbs_g is None
            and self.calories is None
        )


@dataclass(frozen=True)
class MacroTargetView:
    available: bool
    reason: str | None
    protein_g: Decimal | None
    fat_g: Decimal | None
    carbs_g: Decimal | None
    calories: int | None


def macro_calories(*, protein_g: Decimal, carbs_g: Decimal, fat_g: Decimal) -> Decimal:
    """Б×4 + У×4 + Ж×9. Отдельного округления сверх одной десятой нет."""
    raw = protein_g * 4 + carbs_g * 4 + fat_g * 9
    return raw.quantize(_GRAM, rounding=ROUND_HALF_UP)


def target_macros(
    *,
    goal: str | None,
    weight_kg: Number | None,
    body_fat_percent: Number | None,
) -> MacroTarget:
    """Цель БЖУ на день из цели профиля, веса и процента жира.

    Калории: поддержание по Кэтчу–МакАрдлу от массы без жира, затем ±250 ккал по цели.
    Белок и жиры — г/кг массы тела внутри диапазонов 4.10. Жиры не ниже 20% калорий.
    Остаток калорий — углеводы. Если цели или замера не хватает, либо белок и жиры
    не умещаются в калории, возвращается пустой результат.
    """
    if goal not in PROTEIN_G_PER_KG or weight_kg is None or body_fat_percent is None:
        return MacroTarget()
    weight = _as_decimal(weight_kg)
    fat_percent = _as_decimal(body_fat_percent)
    if weight is None or fat_percent is None:
        return MacroTarget()
    if weight <= 0 or fat_percent <= 0 or fat_percent >= 100:
        return MacroTarget()

    lean_kg = weight * (1 - fat_percent / Decimal(100))
    if lean_kg <= 0:
        return MacroTarget()
    bmr = KATCH_INTERCEPT + KATCH_PER_KG_LBM * lean_kg
    calories = _round_kcal(bmr * TRAINING_ACTIVITY) + GOAL_KCAL_DELTA[goal]
    if calories <= 0:
        return MacroTarget()

    protein = (PROTEIN_G_PER_KG[goal] * weight).quantize(_GRAM, rounding=ROUND_HALF_UP)
    fat_from_weight = FAT_G_PER_KG[goal] * weight
    fat_from_calories = Decimal(calories) * FAT_CALORIE_SHARE / Decimal(9)
    fat = max(fat_from_weight, fat_from_calories).quantize(_GRAM, rounding=ROUND_CEILING)
    remaining = Decimal(calories) - protein * 4 - fat * 9
    if remaining < 0:
        return MacroTarget()
    carbs = (remaining / 4).quantize(_GRAM, rounding=ROUND_HALF_UP)
    if carbs < 0:
        return MacroTarget()
    return MacroTarget(protein_g=protein, fat_g=fat, carbs_g=carbs, calories=calories)


def unavailable_macro_target() -> MacroTargetView:
    """Заглушка, пока нет замера. Ничего не читает и не записывает."""
    return MacroTargetView(
        available=False,
        reason=NO_INBODY_SCAN_REASON,
        protein_g=None,
        fat_g=None,
        carbs_g=None,
        calories=None,
    )


def present_intake(row: NutritionIntake | None) -> IntakeView:
    if row is None:
        return IntakeView(None, None, None, None)
    return IntakeView(
        protein_g=row.protein_g,
        fat_g=row.fat_g,
        carbs_g=row.carbs_g,
        calories=macro_calories(protein_g=row.protein_g, carbs_g=row.carbs_g, fat_g=row.fat_g),
    )


async def get_intake(db: AsyncSession, user_id: uuid.UUID) -> NutritionIntake | None:
    """Строка только этого пользователя. Чужая запись этим запросом не находится."""
    return await db.scalar(select(NutritionIntake).where(NutritionIntake.user_id == user_id))


async def save_intake(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    protein_g: float,
    fat_g: float,
    carbs_g: float,
) -> NutritionIntake:
    """Создаёт или заменяет граммы. Сессию не коммитит."""
    protein = _grams(protein_g)
    fat = _grams(fat_g)
    carbs = _grams(carbs_g)
    row = await get_intake(db, user_id)
    if row is None:
        row = NutritionIntake(user_id=user_id, protein_g=protein, fat_g=fat, carbs_g=carbs)
        db.add(row)
        return row
    row.protein_g = protein
    row.fat_g = fat
    row.carbs_g = carbs
    return row


def _grams(value: float) -> Decimal:
    return Decimal(str(value)).quantize(_GRAM, rounding=ROUND_HALF_UP)


def _round_kcal(value: Decimal) -> int:
    return int(value.quantize(_KCAL, rounding=ROUND_HALF_UP))


def _as_decimal(value: Number) -> Decimal | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            return None
        return Decimal(str(value))
    return None
