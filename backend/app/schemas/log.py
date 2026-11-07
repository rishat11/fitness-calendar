import datetime as dt
import uuid

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.exercise import Equipment, WeightType
from app.schemas.plan import PlanSetSnapshot
from app.schemas.profile import WeightUnit

MAX_SETS = 30
MAX_ITEMS = 40
# 5 хранится как «4+»: в шаблоне целевой RIR тоже допускает 5.
RIR_PLUS = 5


def _blank_to_none(value: object) -> object:
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return value


class SetWrite(BaseModel):
    """Полная замена полей подхода: клиент шлёт актуальное состояние при автосохранении."""

    weight: float | None = Field(default=None, ge=0, le=2000)
    extra_weight: float | None = Field(default=None, ge=0, le=2000)
    reps: int | None = Field(default=None, ge=0, le=999)
    rir: int | None = Field(default=None, ge=0, le=RIR_PLUS)
    is_warmup: bool = False
    is_assisted: bool = False
    is_negative: bool = False
    note: str | None = Field(default=None, max_length=500)

    @field_validator("note", mode="before")
    @classmethod
    def clean_note(cls, value: object) -> object:
        return _blank_to_none(value)


class SetCreate(SetWrite):
    """Новый подход. id задаёт клиент, чтобы повтор запроса после обрыва не создал второй подход."""

    id: uuid.UUID | None = None
    position: int | None = Field(default=None, ge=0, le=MAX_SETS)


class SetLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    position: int
    exercise_id: uuid.UUID | None
    weight: float | None
    extra_weight: float | None
    reps: int | None
    rir: int | None
    is_warmup: bool
    is_assisted: bool
    is_negative: bool
    note: str | None


class ItemCreate(BaseModel):
    exercise_id: uuid.UUID
    id: uuid.UUID | None = None
    set_id: uuid.UUID | None = None


class ExerciseReplace(BaseModel):
    exercise_id: uuid.UUID


class NoteWrite(BaseModel):
    note: str | None = Field(default=None, max_length=2000)

    @field_validator("note", mode="before")
    @classmethod
    def clean_note(cls, value: object) -> object:
        return _blank_to_none(value)


class PerformedSummary(BaseModel):
    """Рабочие подходы: все, кроме разминки, у которых указаны повторы."""

    working_sets: int
    volume: float
    unit: WeightUnit | None


class PerformedItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    position: int
    exercise_id: uuid.UUID | None
    name: str
    equipment: Equipment
    weight_type: WeightType
    weight_unit: WeightUnit
    weight_step: float
    note: str | None
    targets: list[PlanSetSnapshot]
    sets: list[SetLogResponse]


class PerformedWorkoutResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    planned_id: uuid.UUID | None
    date: dt.date
    name: str | None
    note: str | None
    started_at: dt.datetime
    finished_at: dt.datetime | None
    items: list[PerformedItemResponse]
    summary: PerformedSummary


class PreviousSets(BaseModel):
    """Подходы упражнения из последней другой тренировки."""

    performed_id: uuid.UUID
    date: dt.date
    sets: list[SetLogResponse]


class PerformedStart(BaseModel):
    planned_id: uuid.UUID
