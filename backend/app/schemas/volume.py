import datetime as dt
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.exercise import Muscle

# below — меньше нижней границы ориентира, in_range — внутри, above — выше верхней.
VolumeStatus = Literal["below", "in_range", "above"]


class MuscleVolumeGroup(BaseModel):
    """Рабочие подходы группы за неделю. muscle = null — «Без группы» (упражнение удалено).

    Для «Без группы» ориентира нет: target_min, target_max и status равны null.
    """

    muscle: Muscle | None
    sets: int = Field(ge=1)
    target_min: int | None
    target_max: int | None
    status: VolumeStatus | None


class VolumeWeekResponse(BaseModel):
    """Календарная неделя пн–вс, в которую входит запрошенная дата. Пустые группы не выводятся."""

    week_start: dt.date
    week_end: dt.date
    groups: list[MuscleVolumeGroup]
