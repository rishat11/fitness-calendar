import datetime as dt
import uuid
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.exercise import Equipment, Muscle, WeightType
from app.schemas.profile import WeightUnit
from app.schemas.workout import WorkoutName

PlanKind = Literal["workout", "rest"]
PlanStatus = Literal["planned", "done", "skipped", "moved"]
Weekday = Annotated[int, Field(ge=0, le=6)]

MAX_CYCLE_WEEKS = 52


class PlanExerciseSnapshot(BaseModel):
    """Упражнение на момент постановки в план: правка справочника план не меняет."""

    exercise_id: uuid.UUID
    name: str
    primary_muscle: Muscle
    equipment: Equipment
    weight_type: WeightType
    weight_unit: WeightUnit
    weight_step: float


class PlanSetSnapshot(BaseModel):
    rep_min: int
    rep_max: int
    target_rir: int | None
    rest_seconds: int | None


class PlanItemSnapshot(BaseModel):
    position: int
    exercise: PlanExerciseSnapshot
    sets: list[PlanSetSnapshot]


class PlanEntryCreate(BaseModel):
    """Тренировка из библиотеки (template_id) или с нуля (name), либо день отдыха (kind=rest)."""

    date: dt.date
    kind: PlanKind = "workout"
    template_id: uuid.UUID | None = None
    name: WorkoutName | None = None

    @model_validator(mode="after")
    def check_source(self) -> Self:
        if self.kind == "rest":
            if self.template_id is not None or self.name is not None:
                raise ValueError("у дня отдыха не может быть названия или шаблона")
        elif (self.template_id is None) == (self.name is None):
            raise ValueError("укажите либо шаблон из библиотеки, либо название")
        return self


class PlanEntryUpdate(BaseModel):
    """Частичное обновление: перенос на дату, смена статуса, признак фиксации."""

    date: dt.date | None = None
    status: PlanStatus | None = None
    is_fixed: bool | None = None


class PlanCycleCreate(BaseModel):
    """Повторяющаяся тренировка: например, пн, ср, пт на 8 недель от даты старта."""

    template_id: uuid.UUID
    start_date: dt.date
    weekdays: list[Weekday] = Field(min_length=1, max_length=7)
    weeks: int = Field(ge=1, le=MAX_CYCLE_WEEKS)

    @model_validator(mode="after")
    def check_weekdays(self) -> Self:
        if len(set(self.weekdays)) != len(self.weekdays):
            raise ValueError("дни недели не должны повторяться")
        return self


ShiftOperation = Literal["shift_following", "shift_only", "skip", "swap"]
ShiftResolution = Literal["cascade", "stack", "cancel"]
ConflictReason = Literal["occupied", "blocked"]


class PlanShiftRequest(BaseModel):
    """Предпросмотр и применение сдвига используют одно и то же тело запроса."""

    operation: ShiftOperation
    entry_id: uuid.UUID
    days: int | None = Field(default=None, ge=-366, le=366)
    other_id: uuid.UUID | None = None
    resolution: ShiftResolution | None = None

    @model_validator(mode="after")
    def check_operation(self) -> Self:
        if self.operation in ("shift_following", "shift_only"):
            if self.days is None or self.days == 0:
                raise ValueError("укажите число дней, отличное от нуля")
        if self.operation == "swap":
            if self.other_id is None:
                raise ValueError("укажите вторую тренировку")
            if self.other_id == self.entry_id:
                raise ValueError("нельзя поменять тренировку саму с собой")
        return self


class PlanShiftChange(BaseModel):
    id: uuid.UUID
    name: str | None
    kind: PlanKind
    date_before: dt.date
    date_after: dt.date
    status_before: PlanStatus | None
    status_after: PlanStatus | None


class PlanShiftConflict(BaseModel):
    entry_id: uuid.UUID
    date: dt.date
    reason: ConflictReason
    message: str


class PlanShiftPreview(BaseModel):
    """Прямой сдвиг и, если день занят, варианты: цепочка дальше, две в день, отмена."""

    changes: list[PlanShiftChange]
    conflicts: list[PlanShiftConflict]
    resolutions: list[ShiftResolution]


class PlanShiftResult(BaseModel):
    applied: bool
    changes: list[PlanShiftChange]
    log_id: uuid.UUID | None


class PlanChangeLogItem(BaseModel):
    id: uuid.UUID
    created_at: dt.datetime
    operation: ShiftOperation
    change_count: int


class PlanEntryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    date: dt.date
    kind: PlanKind
    # null у дня отдыха: статуса у отдыха нет.
    status: PlanStatus | None
    is_fixed: bool
    position: int
    template_id: uuid.UUID | None
    name: str | None
    items: list[PlanItemSnapshot]


# none — лог не начат, open — начат и не завершён, finished — тренировка закрыта.
TodayLogState = Literal["none", "open", "finished"]


class TodayEntryResponse(PlanEntryResponse):
    """Запись выбранного дня и состояние её лога."""

    log_state: TodayLogState


class TodayResponse(BaseModel):
    date: dt.date
    entries: list[TodayEntryResponse]
    # Полный экспорт не скачивали больше месяца, и аккаунту уже больше месяца.
    export_reminder: bool = False
