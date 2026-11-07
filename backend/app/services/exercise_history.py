"""История упражнения для карточки: заметки, подходы и лучшая точка сессии.

Подсказку прогрессии модуль не считает — её отдаёт `/api/progression`.
Лучший рабочий подход и расчётный 1ПМ берутся из `best_working_point`,
теми же правилами, что и подсказка. Нагрузка считается по снимку
`PerformedItem`, поэтому правка справочника старые веса не переписывает.
Удалённое упражнение (`exercise_id` пустой) в выборку не попадает.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.log import PerformedItem, PerformedWorkout, SetLog
from app.schemas.exercise import (
    ExerciseHistory,
    ExerciseHistoryBest,
    ExerciseHistorySession,
    ExerciseHistorySet,
)
from app.services.exercises import get_exercise
from app.services.progression import SetInput, best_working_point


def _visible(logged: SetLog) -> bool:
    return (
        logged.weight is not None
        or logged.extra_weight is not None
        or logged.reps is not None
        or logged.rir is not None
        or logged.is_warmup
        or logged.is_assisted
        or logged.is_negative
    )


def _session(workout: PerformedWorkout, exercise_id: uuid.UUID) -> ExerciseHistorySession | None:
    items = sorted(
        (item for item in workout.items if item.exercise_id == exercise_id),
        key=lambda item: item.position,
    )
    if not items:
        return None
    notes = [item.note.strip() for item in items if item.note and item.note.strip()]
    visible: list[tuple[PerformedItem, SetLog]] = []
    inputs: list[SetInput] = []
    position = 0
    for item in items:
        for logged in sorted(item.sets, key=lambda row: row.position):
            inputs.append(
                SetInput(
                    position=position,
                    weight=logged.weight,
                    extra_weight=logged.extra_weight,
                    reps=logged.reps,
                    rir=logged.rir,
                    is_warmup=logged.is_warmup,
                    is_assisted=logged.is_assisted,
                    is_negative=logged.is_negative,
                    weight_type=item.weight_type,
                    weight_step=item.weight_step,
                    weight_unit=item.weight_unit,
                )
            )
            position += 1
            if _visible(logged):
                visible.append((item, logged))
    picked = best_working_point(inputs)
    best = None
    if picked is not None:
        winner, point = picked
        unit = winner.weight_unit if winner.weight_unit in {"kg", "lb"} else None
        best = ExerciseHistoryBest(
            load=point.load,
            reps=point.reps,
            epley_1rm=point.epley_1rm,
            weight_unit=unit,  # type: ignore[arg-type]
        )
    if not notes and not visible:
        return None
    return ExerciseHistorySession(
        performed_id=workout.id,
        date=workout.date,
        started_at=workout.started_at,
        notes=notes,
        sets=[
            ExerciseHistorySet(
                weight=logged.weight,
                extra_weight=logged.extra_weight,
                reps=logged.reps,
                rir=logged.rir,
                is_warmup=logged.is_warmup,
                is_assisted=logged.is_assisted,
                is_negative=logged.is_negative,
                weight_unit=item.weight_unit,  # type: ignore[arg-type]
            )
            for item, logged in visible
        ],
        best=best,
    )


async def exercise_history(
    db: AsyncSession, user_id: uuid.UUID, exercise_id: uuid.UUID
) -> ExerciseHistory | None:
    """None — упражнения нет у этого пользователя. Чужой id тоже None."""
    exercise = await get_exercise(db, user_id, exercise_id)
    if exercise is None:
        return None
    workouts = list(
        await db.scalars(
            select(PerformedWorkout)
            .where(
                PerformedWorkout.user_id == user_id,
                PerformedWorkout.finished_at.is_not(None),
                PerformedWorkout.items.any(PerformedItem.exercise_id == exercise_id),
            )
            .options(selectinload(PerformedWorkout.items).selectinload(PerformedItem.sets))
            .order_by(
                PerformedWorkout.date.desc(),
                PerformedWorkout.started_at.desc(),
                PerformedWorkout.id.desc(),
            )
        )
    )
    sessions: list[ExerciseHistorySession] = []
    for workout in workouts:
        session = _session(workout, exercise_id)
        if session is not None:
            sessions.append(session)
    return ExerciseHistory(sessions=sessions)
