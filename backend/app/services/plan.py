import datetime as dt
import uuid
from collections import defaultdict
from collections.abc import Iterable, Sequence
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.plan import (
    KIND_REST,
    KIND_WORKOUT,
    STATUS_DONE,
    STATUS_MOVED,
    STATUS_PLANNED,
    STATUS_SKIPPED,
    PlannedWorkout,
)
from app.models.workout import WorkoutTemplate
from app.schemas.plan import PlanExerciseSnapshot, PlanItemSnapshot, PlanSetSnapshot

MAX_RANGE_DAYS = 366

# Из запланированной тренировки можно отметить результат. Итоговый статус возвращается
# в «запланирована» только для исправления ошибки. Перенос и сдвиг работают лишь с «запланирована».
STATUS_TRANSITIONS: dict[str, frozenset[str]] = {
    STATUS_PLANNED: frozenset({STATUS_DONE, STATUS_SKIPPED, STATUS_MOVED}),
    STATUS_DONE: frozenset({STATUS_PLANNED}),
    STATUS_SKIPPED: frozenset({STATUS_PLANNED}),
    STATUS_MOVED: frozenset({STATUS_PLANNED}),
}


class PlanConflictError(Exception):
    """Нарушено правило плана: например, день отдыха занят тренировкой или запись не переносится."""


async def list_entries(
    db: AsyncSession, user_id: uuid.UUID, start: dt.date, end: dt.date
) -> Sequence[PlannedWorkout]:
    result = await db.scalars(
        select(PlannedWorkout)
        .where(
            PlannedWorkout.user_id == user_id,
            PlannedWorkout.date >= start,
            PlannedWorkout.date <= end,
        )
        .order_by(PlannedWorkout.date, PlannedWorkout.position, PlannedWorkout.id)
    )
    return result.all()


async def get_entry(
    db: AsyncSession, user_id: uuid.UUID, entry_id: uuid.UUID
) -> PlannedWorkout | None:
    """Возвращает запись только если она принадлежит пользователю."""
    return await db.scalar(
        select(PlannedWorkout).where(
            PlannedWorkout.id == entry_id, PlannedWorkout.user_id == user_id
        )
    )


async def _lock_user_plan(db: AsyncSession, user_id: uuid.UUID) -> None:
    """Сериализует изменения плана одного пользователя до конца транзакции.

    Проверки «день занят» читают записи и затем пишут новые. Без блокировки два параллельных
    запроса (двойной клик, две вкладки) могут пройти проверку одновременно и нарушить правила.
    Блокировка снимается сама при commit или rollback.
    """
    await db.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": f"plan:{user_id}"}
    )


async def _entries_on_day(
    db: AsyncSession, user_id: uuid.UUID, day: dt.date, exclude_id: uuid.UUID | None = None
) -> list[PlannedWorkout]:
    query = select(PlannedWorkout).where(
        PlannedWorkout.user_id == user_id, PlannedWorkout.date == day
    )
    if exclude_id is not None:
        query = query.where(PlannedWorkout.id != exclude_id)
    result = await db.scalars(query)
    return list(result.all())


async def _entries_by_date(
    db: AsyncSession, user_id: uuid.UUID, start: dt.date, end: dt.date
) -> dict[dt.date, list[PlannedWorkout]]:
    by_date: dict[dt.date, list[PlannedWorkout]] = defaultdict(list)
    for entry in await list_entries(db, user_id, start, end):
        by_date[entry.date].append(entry)
    return by_date


def _next_position(entries: Iterable[PlannedWorkout]) -> int:
    return max((entry.position for entry in entries), default=-1) + 1


def _ensure_day_allows(existing: Sequence[PlannedWorkout], kind: str) -> None:
    """День либо отдых (он единственная запись), либо тренировки. Совмещать нельзя."""
    if kind == KIND_REST:
        if existing:
            raise PlanConflictError("На этот день уже что-то запланировано")
    elif any(entry.kind == KIND_REST for entry in existing):
        raise PlanConflictError("Этот день отмечен как отдых")


def snapshot_from_template(template: WorkoutTemplate) -> list[dict[str, Any]]:
    """Копирует структуру шаблона в снимок. Дальше снимок не зависит от библиотеки."""
    return [
        PlanItemSnapshot(
            position=item.position,
            exercise=PlanExerciseSnapshot(
                exercise_id=item.exercise.id,
                name=item.exercise.name,
                primary_muscle=item.exercise.primary_muscle,
                equipment=item.exercise.equipment,
                weight_type=item.exercise.weight_type,
                weight_unit=item.exercise.weight_unit,
                weight_step=item.exercise.weight_step,
            ),
            sets=[
                PlanSetSnapshot(
                    rep_min=set_.rep_min,
                    rep_max=set_.rep_max,
                    target_rir=set_.target_rir,
                    rest_seconds=set_.rest_seconds,
                )
                for set_ in item.sets
            ],
        ).model_dump(mode="json")
        for item in template.items
    ]


def _workout_entry(
    user_id: uuid.UUID,
    day: dt.date,
    position: int,
    *,
    name: str,
    template: WorkoutTemplate | None,
) -> PlannedWorkout:
    return PlannedWorkout(
        user_id=user_id,
        date=day,
        kind=KIND_WORKOUT,
        template_id=template.id if template else None,
        name=name,
        snapshot=snapshot_from_template(template) if template else [],
        status=STATUS_PLANNED,
        is_fixed=False,
        position=position,
    )


async def create_entry(
    db: AsyncSession,
    user_id: uuid.UUID,
    day: dt.date,
    *,
    template: WorkoutTemplate | None = None,
    name: str | None = None,
) -> PlannedWorkout:
    """Тренировка из шаблона (со снимком) или с нуля по названию."""
    await _lock_user_plan(db, user_id)
    existing = await _entries_on_day(db, user_id, day)
    _ensure_day_allows(existing, KIND_WORKOUT)
    title = template.name if template is not None else (name or "")
    entry = _workout_entry(
        user_id,
        day,
        _next_position(existing),
        name=title,
        template=template,
    )
    db.add(entry)
    await db.flush()
    return entry


async def create_rest(db: AsyncSession, user_id: uuid.UUID, day: dt.date) -> PlannedWorkout:
    await _lock_user_plan(db, user_id)
    existing = await _entries_on_day(db, user_id, day)
    _ensure_day_allows(existing, KIND_REST)
    entry = PlannedWorkout(
        user_id=user_id,
        date=day,
        kind=KIND_REST,
        snapshot=[],
        position=0,
        is_fixed=False,
    )
    db.add(entry)
    await db.flush()
    return entry


async def create_cycle(
    db: AsyncSession,
    user_id: uuid.UUID,
    template: WorkoutTemplate,
    *,
    start: dt.date,
    weekdays: set[int],
    weeks: int,
) -> list[PlannedWorkout]:
    """Ставит тренировку во все выбранные дни недели на `weeks` недель от даты старта.

    Проверка всех дней до записи: если хоть один день занят отдыхом, ничего не создаётся.
    """
    await _lock_user_plan(db, user_id)
    end = start + dt.timedelta(days=weeks * 7 - 1)
    days = [start + dt.timedelta(days=offset) for offset in range(weeks * 7)]
    days = [day for day in days if day.weekday() in weekdays]

    by_date = await _entries_by_date(db, user_id, start, end)
    for day in days:
        _ensure_day_allows(by_date.get(day, []), KIND_WORKOUT)

    created: list[PlannedWorkout] = []
    for day in days:
        entry = _workout_entry(
            user_id,
            day,
            _next_position(by_date.get(day, [])),
            name=template.name,
            template=template,
        )
        db.add(entry)
        by_date[day].append(entry)
        created.append(entry)
    await db.flush()
    return created


async def update_entry(
    db: AsyncSession,
    user_id: uuid.UUID,
    entry: PlannedWorkout,
    *,
    day: dt.date | None = None,
    status: str | None = None,
    is_fixed: bool | None = None,
) -> PlannedWorkout:
    if day is not None and day != entry.date:
        # День отдыха статуса не имеет, переносить его можно на любой свободный день.
        if entry.kind == KIND_WORKOUT and entry.status != STATUS_PLANNED:
            raise PlanConflictError("Перенести можно только запланированную запись")
        await _lock_user_plan(db, user_id)
        existing = await _entries_on_day(db, user_id, day, exclude_id=entry.id)
        _ensure_day_allows(existing, entry.kind)
        entry.date = day
        entry.position = _next_position(existing)

    if status is not None:
        if entry.kind == KIND_REST:
            raise PlanConflictError("У дня отдыха нет статуса")
        if status != entry.status:
            allowed = STATUS_TRANSITIONS.get(entry.status or "", frozenset())
            if status not in allowed:
                raise PlanConflictError(f"Нельзя сменить статус «{entry.status}» на «{status}»")
        entry.status = status

    if is_fixed is not None:
        entry.is_fixed = is_fixed

    await db.flush()
    return entry


async def delete_entry(db: AsyncSession, entry: PlannedWorkout) -> None:
    await db.delete(entry)
    await db.flush()
