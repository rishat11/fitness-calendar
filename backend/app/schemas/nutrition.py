from decimal import Decimal

from pydantic import BaseModel, Field


def number_from_decimal(value: Decimal | None) -> float | None:
    if value is None:
        return None
    if value == value.to_integral_value():
        return float(int(value))
    return float(value)


class IntakeUpdate(BaseModel):
    """Полная замена текущего БЖУ. Калории клиент не присылает."""

    protein_g: float = Field(ge=0, le=2000)
    fat_g: float = Field(ge=0, le=2000)
    carbs_g: float = Field(ge=0, le=2000)


class IntakeResponse(BaseModel):
    protein_g: float | None
    fat_g: float | None
    carbs_g: float | None
    calories: float | None


class MacroTargetResponse(BaseModel):
    available: bool
    reason: str | None
    protein_g: float | None
    fat_g: float | None
    carbs_g: float | None
    calories: int | None
