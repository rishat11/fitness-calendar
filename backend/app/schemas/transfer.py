import datetime as dt
import uuid
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.exercise import Equipment, ExerciseInput, WeightType
from app.schemas.log import SetWrite
from app.schemas.plan import PlanItemSnapshot, PlanKind, PlanStatus
from app.schemas.profile import ProfileUpdate, WeightUnit
from app.schemas.workout import WorkoutSetInput

FORMAT_VERSION = 1
ShiftOperation = Literal["shift_following", "shift_only", "skip", "swap"]
ShiftResolution = Literal["cascade", "stack", "cancel"]

MAX_EXERCISES = 5_000
MAX_TEMPLATES = 2_000
MAX_ITEMS = 50
MAX_SETS = 30
MAX_PLANNED = 20_000
MAX_PERFORMED = 10_000
MAX_CHANGE_LOGS = 20
MAX_DECISIONS = 10_000


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ExerciseExport(ExerciseInput):
    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    archived: bool


class TemplateSetExport(WorkoutSetInput):
    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    position: int = Field(ge=0)


class TemplateItemExport(_Strict):
    id: uuid.UUID
    exercise_id: uuid.UUID
    position: int = Field(ge=0)
    sets: list[TemplateSetExport] = Field(min_length=1, max_length=MAX_SETS)


class WorkoutTemplateExport(_Strict):
    id: uuid.UUID
    name: str = Field(min_length=1, max_length=120)
    created_at: dt.datetime
    items: list[TemplateItemExport] = Field(default_factory=list, max_length=MAX_ITEMS)


class PlannedWorkoutExport(_Strict):
    id: uuid.UUID
    date: dt.date
    kind: PlanKind
    template_id: uuid.UUID | None
    name: str | None = Field(default=None, max_length=120)
    snapshot: list[PlanItemSnapshot] = Field(default_factory=list, max_length=MAX_ITEMS)
    status: PlanStatus | None
    is_fixed: bool
    position: int = Field(ge=0)
    created_at: dt.datetime

    @model_validator(mode="after")
    def check_kind(self) -> Self:
        if self.kind == "rest":
            if self.status is not None or self.name is not None or self.template_id is not None:
                raise ValueError("у дня отдыха нет статуса, названия и шаблона")
            if self.snapshot:
                raise ValueError("у дня отдыха нет снимка тренировки")
        elif self.status is None or self.name is None:
            raise ValueError("у тренировки обязательны название и статус")
        return self


class PlanChangeItemExport(_Strict):
    id: uuid.UUID
    date: dt.date
    status: PlanStatus | None
    position: int = Field(ge=0)


class PlanChangePayloadExport(_Strict):
    operation: ShiftOperation
    days: int | None = None
    resolution: ShiftResolution | None = None
    changes: list[PlanChangeItemExport] = Field(max_length=MAX_PLANNED)


class PlanChangeLogExport(_Strict):
    id: uuid.UUID
    operation: ShiftOperation
    payload: PlanChangePayloadExport
    created_at: dt.datetime


class SetLogExport(SetWrite):
    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    position: int = Field(ge=0)
    exercise_id: uuid.UUID | None


class PerformedItemExport(_Strict):
    id: uuid.UUID
    position: int = Field(ge=0)
    exercise_id: uuid.UUID | None
    name: str = Field(min_length=1, max_length=120)
    equipment: Equipment
    weight_type: WeightType
    weight_unit: WeightUnit
    weight_step: float = Field(gt=0, le=100)
    note: str | None = Field(default=None, max_length=2000)
    targets: list[WorkoutSetInput] = Field(default_factory=list, max_length=MAX_SETS)
    sets: list[SetLogExport] = Field(default_factory=list, max_length=MAX_SETS)


class ProgressionDecisionExport(_Strict):
    id: uuid.UUID
    exercise_id: uuid.UUID
    status: Literal["increase_weight", "continue", "stagnation"]
    last_session_id: uuid.UUID
    suggested_weight: float | None = None
    action: Literal["accept", "reject"]
    created_at: dt.datetime


class PerformedWorkoutExport(_Strict):
    id: uuid.UUID
    planned_id: uuid.UUID | None
    date: dt.date
    name: str | None = Field(default=None, max_length=120)
    note: str | None = Field(default=None, max_length=2000)
    started_at: dt.datetime
    finished_at: dt.datetime | None
    items: list[PerformedItemExport] = Field(default_factory=list, max_length=MAX_ITEMS)


class ExportDocument(_Strict):
    """Полный снимок данных одного пользователя. Версия формата позволяет читать старые файлы."""

    format_version: Literal[1]
    exported_at: dt.datetime
    profile: ProfileUpdate
    exercises: list[ExerciseExport] = Field(max_length=MAX_EXERCISES)
    workout_templates: list[WorkoutTemplateExport] = Field(max_length=MAX_TEMPLATES)
    planned_workouts: list[PlannedWorkoutExport] = Field(max_length=MAX_PLANNED)
    plan_change_logs: list[PlanChangeLogExport] = Field(max_length=MAX_CHANGE_LOGS)
    performed_workouts: list[PerformedWorkoutExport] = Field(max_length=MAX_PERFORMED)
    progression_decisions: list[ProgressionDecisionExport] = Field(
        default_factory=list, max_length=MAX_DECISIONS
    )


class ImportResult(_Strict):
    exercises: int
    workout_templates: int
    planned_workouts: int
    performed_workouts: int
