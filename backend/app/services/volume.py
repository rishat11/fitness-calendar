"""Объём по мышечным группам: число рабочих подходов за календарную неделю (пн–вс).

Считается число подходов, а не тоннаж. Группа подхода — текущая primary_muscle упражнения
по exercise_id. Если упражнение удалено, exercise_id пустой и подход попадает в «Без группы».
Вторичные группы в объём не входят. Разминка и подходы без повторов не считаются.
"""

import datetime as dt
import uuid
from collections.abc import Sequence
from typing import cast

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.exercise import Exercise
from app.models.log import PerformedWorkout, SetLog
from app.schemas.exercise import Muscle
from app.schemas.volume import MuscleVolumeGroup, VolumeStatus, VolumeWeekResponse

# Ориентир для гипертрофии на группу за неделю: визуальная полоса, не ограничение.
TARGET_MIN = 10
TARGET_MAX = 20


def week_bounds(day: dt.date) -> tuple[dt.date, dt.date]:
    """Понедельник и воскресенье недели, в которую входит день."""
    start = day - dt.timedelta(days=day.weekday())
    return start, start + dt.timedelta(days=6)


def target_status(sets: int) -> VolumeStatus:
    if sets < TARGET_MIN:
        return "below"
    if sets > TARGET_MAX:
        return "above"
    return "in_range"


def build_groups(counts: Sequence[tuple[str | None, int]]) -> list[MuscleVolumeGroup]:
    """Группы с подходами больше нуля: от большего числа к меньшему, «Без группы» в конце."""
    groups: list[MuscleVolumeGroup] = []
    for muscle, sets in counts:
        if sets <= 0:
            continue
        if muscle is None:
            groups.append(
                MuscleVolumeGroup(
                    muscle=None, sets=sets, target_min=None, target_max=None, status=None
                )
            )
            continue
        groups.append(
            MuscleVolumeGroup(
                # Значения в базе проверяются схемой упражнения, поэтому сужаем тип без проверки.
                muscle=cast(Muscle, muscle),
                sets=sets,
                target_min=TARGET_MIN,
                target_max=TARGET_MAX,
                status=target_status(sets),
            )
        )
    return sorted(groups, key=lambda group: (-group.sets, group.muscle is None, group.muscle or ""))


async def muscle_volume(db: AsyncSession, user_id: uuid.UUID, day: dt.date) -> VolumeWeekResponse:
    start, end = week_bounds(day)
    rows = await db.execute(
        select(Exercise.primary_muscle, func.count(SetLog.id))
        .select_from(SetLog)
        .join(PerformedWorkout, SetLog.performed_id == PerformedWorkout.id)
        .outerjoin(
            Exercise,
            and_(Exercise.id == SetLog.exercise_id, Exercise.user_id == user_id),
        )
        .where(
            PerformedWorkout.user_id == user_id,
            PerformedWorkout.date >= start,
            PerformedWorkout.date <= end,
            SetLog.is_warmup.is_(False),
            SetLog.reps.is_not(None),
        )
        .group_by(Exercise.primary_muscle)
    )
    counts = [(muscle, int(total)) for muscle, total in rows.all()]
    return VolumeWeekResponse(week_start=start, week_end=end, groups=build_groups(counts))
