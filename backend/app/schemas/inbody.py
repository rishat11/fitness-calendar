import datetime as dt
import uuid
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

DeltaCode = Literal[
    "weight_kg",
    "smm_kg",
    "bfm_kg",
    "pbf_percent",
    "tbw_l",
    "visceral_fat_level",
]
DeltaUnit = Literal["kg", "l", "pp", "level"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SegmentPart(_Strict):
    """Килограммы мышц и жира одного сегмента. Оба числа необязательны."""

    muscle_kg: float | None = Field(default=None, ge=0, le=100)
    fat_kg: float | None = Field(default=None, ge=0, le=100)


class Segments(_Strict):
    right_arm: SegmentPart | None = None
    left_arm: SegmentPart | None = None
    trunk: SegmentPart | None = None
    right_leg: SegmentPart | None = None
    left_leg: SegmentPart | None = None

    @model_validator(mode="after")
    def not_empty(self) -> Self:
        parts = (self.right_arm, self.left_arm, self.trunk, self.right_leg, self.left_leg)
        if all(part is None for part in parts):
            raise ValueError("укажите хотя бы один сегмент или не присылайте сегменты")
        return self


class InbodyScanInput(_Strict):
    measured_on: dt.date
    measured_time: dt.time | None = None
    weight_kg: float = Field(ge=20, le=400)
    smm_kg: float = Field(ge=0, le=200)
    bfm_kg: float = Field(ge=0, le=300)
    pbf_percent: float = Field(ge=0.1, le=80)
    tbw_l: float = Field(ge=1, le=200)
    visceral_fat_level: int = Field(ge=1, le=30)
    bmr_kcal: int = Field(ge=500, le=6000)
    segments: Segments | None = None


class MetricDeltaResponse(_Strict):
    code: DeltaCode
    absolute: float
    relative_percent: float | None
    unit: DeltaUnit


class InbodyScanResponse(InbodyScanInput):
    id: uuid.UUID
    deltas: list[MetricDeltaResponse]


class InbodyParseResponse(_Strict):
    """Цифры с листа. Пустые поля — то, что в PDF не нашлось. Замер этим ответом не создаётся."""

    measured_on: dt.date | None
    measured_time: dt.time | None
    weight_kg: float | None
    smm_kg: float | None
    bfm_kg: float | None
    pbf_percent: float | None
    tbw_l: float | None
    visceral_fat_level: int | None
    bmr_kcal: int | None
    missing: list[str]
