import datetime as dt
import uuid
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.block import MAX_BLOCK_WEEKS, MAX_CYCLE_DAYS
from app.schemas.workout import WorkoutName

WeekType = Literal["high_reps", "hypertrophy", "strength", "deload", "free"]
ScheduleKind = Literal["workout", "rest"]
MAX_SCHEDULE_DAYS = MAX_CYCLE_DAYS


class BlockWeekInput(BaseModel):
    """Параметры одной недели блока. Накладываются на все тренировки этой недели."""

    week_type: WeekType
    rep_min: int = Field(ge=1, le=30)
    rep_max: int = Field(ge=1, le=30)
    target_rir: int = Field(ge=0, le=5)
    # Доля подходов от базового шаблона: 1 — все подходы, 0.5 — половина.
    volume_multiplier: float = Field(gt=0, le=1)

    @model_validator(mode="after")
    def check_reps(self) -> Self:
        if self.rep_min > self.rep_max:
            raise ValueError("нижняя граница повторов больше верхней")
        return self


class BlockScheduleInput(BaseModel):
    """День цикла: тренировка из библиотеки или отдых. Пустой день не задаётся."""

    day_index: int = Field(ge=0, le=MAX_SCHEDULE_DAYS - 1)
    kind: ScheduleKind = "workout"
    template_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def check_source(self) -> Self:
        if self.kind == "workout" and self.template_id is None:
            raise ValueError("укажите тренировку из библиотеки или отметьте день отдыхом")
        if self.kind == "rest" and self.template_id is not None:
            raise ValueError("у дня отдыха не может быть тренировки")
        return self


class BlockInput(BaseModel):
    """Полная замена блока: название, циклы и расписание дней цикла."""

    name: WorkoutName
    # 7 сохраняет прежние недельные блоки, если клиент длину цикла не прислал.
    cycle_days: int = Field(default=7, ge=1, le=MAX_CYCLE_DAYS)
    weeks: list[BlockWeekInput] = Field(min_length=1, max_length=MAX_BLOCK_WEEKS)
    schedule: list[BlockScheduleInput] = Field(max_length=MAX_SCHEDULE_DAYS)

    @model_validator(mode="after")
    def check_schedule(self) -> Self:
        days = [item.day_index for item in self.schedule]
        if len(set(days)) != len(days):
            raise ValueError("день цикла не должен повторяться")
        if any(day >= self.cycle_days for day in days):
            raise ValueError("день выходит за длину цикла")
        if not any(item.kind == "workout" for item in self.schedule):
            raise ValueError("в блоке нужна хотя бы одна тренировка")
        return self


class BlockWeekResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    position: int
    week_type: WeekType
    rep_min: int
    rep_max: int
    target_rir: int
    volume_multiplier: float


class BlockScheduleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    day_index: int
    kind: ScheduleKind
    name: str | None
    template_id: uuid.UUID | None


class BlockResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    length_weeks: int
    cycle_days: int
    weeks: list[BlockWeekResponse]
    schedule: list[BlockScheduleResponse]


class BlockApplyRequest(BaseModel):
    """Дата, с которой блок начинается: первый день первого цикла.

    `repeats` продолжает циклы по кругу без даты конца.
    """

    start_date: dt.date
    repeats: bool = False


class PlacementResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    block_id: uuid.UUID | None
    name: str
    length_weeks: int
    cycle_days: int
    repeats: bool
    start_date: dt.date
    end_date: dt.date | None
