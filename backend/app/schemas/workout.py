import uuid
from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.schemas.exercise import Equipment, Muscle

WorkoutName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]

MAX_ITEMS = 50
MAX_SETS = 20


class WorkoutSetInput(BaseModel):
    """Один подход: свои повторы, RIR и отдых. Подходы в одной позиции могут различаться."""

    rep_min: int = Field(ge=1, le=100)
    rep_max: int = Field(ge=1, le=100)
    target_rir: int | None = Field(default=None, ge=0, le=5)
    rest_seconds: int | None = Field(default=None, ge=0, le=1800)

    @model_validator(mode="after")
    def check_reps(self) -> Self:
        if self.rep_min > self.rep_max:
            raise ValueError("нижняя граница повторов больше верхней")
        return self


class WorkoutItemInput(BaseModel):
    exercise_id: uuid.UUID
    sets: list[WorkoutSetInput] = Field(min_length=1, max_length=MAX_SETS)


class WorkoutTemplateInput(BaseModel):
    """Полная замена тренировки: порядок позиций задаёт порядок в списке."""

    name: WorkoutName
    items: list[WorkoutItemInput] = Field(default_factory=list, max_length=MAX_ITEMS)


class WorkoutRenameInput(BaseModel):
    name: WorkoutName


class WorkoutSetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    rep_min: int
    rep_max: int
    target_rir: int | None
    rest_seconds: int | None


class WorkoutExerciseResponse(BaseModel):
    """Краткие данные упражнения для списка позиций, чтобы не делать второй запрос."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    primary_muscle: Muscle
    equipment: Equipment
    archived: bool


class WorkoutItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    exercise_id: uuid.UUID
    position: int
    exercise: WorkoutExerciseResponse
    sets: list[WorkoutSetResponse]


class WorkoutTemplateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    items: list[WorkoutItemResponse]
