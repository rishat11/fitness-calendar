import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from sqlalchemy import select, text, tuple_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.exercise import Exercise
from app.models.log import PerformedItem, PerformedWorkout, SetLog
from app.models.plan import KIND_WORKOUT, STATUS_DONE, STATUS_PLANNED, PlannedWorkout
from app.schemas.log import (
    MAX_ITEMS,
    MAX_SETS,
    ExerciseReplace,
    ItemCreate,
    NoteWrite,
    PerformedItemResponse,
    PerformedSummary,
    PerformedWorkoutResponse,
    PersonalRecord,
    PreviousSets,
    SetCreate,
    SetLogResponse,
    SetWrite,
)
from app.schemas.plan import PlanItemSnapshot
from app.schemas.profile import WeightUnit
from app.services.exercises import get_exercise
from app.services.plan import resolve_entry

# Гравитрон без веса тела в килограммы объёма не переводится: помощь — не масса снаряда.
ASSISTED_WEIGHT = "bodyweight_assisted"


class LogError(Exception):
    """Запрос к логу нельзя выполнить: день отдыха, чужое упражнение, лимит подходов."""


def set_load(weight_type: str, weight: float | None, extra_weight: float | None) -> float | None:
    """Нагрузка одного повтора. None — объём по этому подходу не считается.

    Гантели умножаются на два: в поле вес одной гантели. Стопка и доп. вес складываются.
    """
    if weight_type == ASSISTED_WEIGHT:
        return None
    if weight is None and extra_weight is None:
        return None
    primary = weight or 0
    extra = extra_weight or 0
    if weight_type == "per_dumbbell":
        return primary * 2
    if weight_type == "stack_plus_extra":
        return primary + extra
    return primary


@dataclass(frozen=True, slots=True)
class _Attempt:
    exercise_id: uuid.UUID
    name: str
    load: float | None
    reps: int
    unit: str


def _record_load(item: PerformedItem, logged: SetLog) -> float | None:
    """Нагрузка подхода. Ноль и гравитрон — не вес для рекорда."""
    raw = set_load(item.weight_type, logged.weight, logged.extra_weight)
    if raw is None:
        return None
    load = round(raw, 2)
    if load <= 0:
        return None
    return load


def _record_attempts(items: Sequence[PerformedItem]) -> list[_Attempt]:
    """Рабочий подход для рекорда: не разминка, не «с помощью», не негативы, есть повторы.

    Вес для рекорда нагрузки и 1ПМ необязателен: без него остаётся только рекорд повторов.
    """
    attempts: list[_Attempt] = []
    for item in sorted(items, key=lambda row: row.position):
        if item.exercise_id is None:
            continue
        for logged in sorted(item.sets, key=lambda row: row.position):
            if logged.is_warmup or logged.is_assisted or logged.is_negative:
                continue
            if logged.reps is None or logged.reps <= 0:
                continue
            attempts.append(
                _Attempt(
                    exercise_id=item.exercise_id,
                    name=item.name,
                    load=_record_load(item, logged),
                    reps=logged.reps,
                    unit=item.weight_unit,
                )
            )
    return attempts


def _epley(load: float | None, reps: int) -> float | None:
    if load is None:
        return None
    return round(load * (1 + reps / 30), 2)


def _unit(value: str) -> WeightUnit | None:
    if value == "kg" or value == "lb":
        return value
    return None


def _personal(kind: Literal["weight", "reps", "epley"], attempt: _Attempt) -> PersonalRecord:
    return PersonalRecord(
        kind=kind,
        exercise_id=attempt.exercise_id,
        name=attempt.name,
        load=attempt.load,
        reps=attempt.reps,
        epley_1rm=_epley(attempt.load, attempt.reps) if kind == "epley" else None,
        unit=_unit(attempt.unit),
    )


def _heaviest(attempts: Sequence[_Attempt]) -> _Attempt | None:
    weighted = [attempt for attempt in attempts if attempt.load is not None]
    if not weighted:
        return None
    return max(weighted, key=lambda attempt: (attempt.load or 0, attempt.reps))


def _weight_record(current: Sequence[_Attempt], earlier: Sequence[_Attempt]) -> _Attempt | None:
    best = _heaviest(current)
    if best is None or best.load is None:
        return None
    previous = _heaviest(earlier)
    if previous is not None and previous.load is not None and best.load <= previous.load:
        return None
    return best


def _reps_record(current: Sequence[_Attempt], earlier: Sequence[_Attempt]) -> _Attempt | None:
    """Больше повторов только при той же нагрузке. Новый вес сам по себе рекорд повторов не даёт.

    Первая сессия упражнения задаёт рекорд повторов лучшим подходом.
    """
    if not current:
        return None
    if not earlier:
        return max(current, key=lambda attempt: (attempt.reps, attempt.load or 0))
    best_reps: dict[float | None, int] = {}
    for attempt in earlier:
        best_reps[attempt.load] = max(attempt.reps, best_reps.get(attempt.load, 0))
    improved = [
        attempt
        for attempt in current
        if attempt.load in best_reps and attempt.reps > best_reps[attempt.load]
    ]
    if not improved:
        return None
    return max(improved, key=lambda attempt: (attempt.reps, attempt.load or 0))


def _top_epley(attempts: Sequence[_Attempt]) -> tuple[_Attempt, float] | None:
    scored = [
        (attempt, score)
        for attempt in attempts
        if (score := _epley(attempt.load, attempt.reps)) is not None
    ]
    if not scored:
        return None
    return max(scored, key=lambda pair: (pair[1], pair[0].load or 0, pair[0].reps))


def _epley_record(current: Sequence[_Attempt], earlier: Sequence[_Attempt]) -> _Attempt | None:
    best = _top_epley(current)
    if best is None:
        return None
    previous = _top_epley(earlier)
    if previous is not None and best[1] <= previous[1]:
        return None
    return best[0]


def records_against(
    current_items: Sequence[PerformedItem], earlier_items: Sequence[PerformedItem]
) -> list[PersonalRecord]:
    """Три независимых рекорда на упражнение: нагрузка, повторы при ней, 1ПМ Эпли.

    Сравнение только с переданной более ранней историей. Равное значение не показывается.
    """
    current = _record_attempts(current_items)
    earlier = _record_attempts(earlier_items)
    grouped: dict[uuid.UUID, list[_Attempt]] = {}
    order: list[uuid.UUID] = []
    for attempt in current:
        if attempt.exercise_id not in grouped:
            order.append(attempt.exercise_id)
            grouped[attempt.exercise_id] = []
        grouped[attempt.exercise_id].append(attempt)
    prior: dict[uuid.UUID, list[_Attempt]] = {}
    for attempt in earlier:
        prior.setdefault(attempt.exercise_id, []).append(attempt)

    found: list[PersonalRecord] = []
    for exercise_id in order:
        rows = grouped[exercise_id]
        history = prior.get(exercise_id, [])
        weight = _weight_record(rows, history)
        if weight is not None:
            found.append(_personal("weight", weight))
        reps = _reps_record(rows, history)
        if reps is not None:
            found.append(_personal("reps", reps))
        epley = _epley_record(rows, history)
        if epley is not None:
            found.append(_personal("epley", epley))
    return found


def summarize(items: list[PerformedItem]) -> PerformedSummary:
    """Число рабочих подходов и объём. Разминка и подходы без повторов не входят."""
    working_sets = 0
    volume = 0.0
    units: set[str] = set()
    for item in items:
        for logged in item.sets:
            if logged.is_warmup or logged.reps is None:
                continue
            working_sets += 1
            load = set_load(item.weight_type, logged.weight, logged.extra_weight)
            if load is None:
                continue
            volume += load * logged.reps
            units.add(item.weight_unit)
    unit = next(iter(units)) if len(units) == 1 else None
    return PerformedSummary(working_sets=working_sets, volume=round(volume, 2), unit=unit)


async def _earlier_items(
    db: AsyncSession, user_id: uuid.UUID, workout: PerformedWorkout
) -> list[PerformedItem]:
    """Те же упражнения в более ранних тренировках только этого пользователя.

    Раньше — календарная дата, затем время начала, затем id. Поздняя сессия
    не отменяет рекорд, который эта тренировка уже поставила.
    """
    exercise_ids = [item.exercise_id for item in workout.items if item.exercise_id is not None]
    if not exercise_ids:
        return []
    rows = await db.scalars(
        select(PerformedItem)
        .join(PerformedWorkout, PerformedItem.performed_id == PerformedWorkout.id)
        .where(
            PerformedWorkout.user_id == user_id,
            PerformedItem.exercise_id.in_(exercise_ids),
            tuple_(PerformedWorkout.date, PerformedWorkout.started_at, PerformedWorkout.id)
            < tuple_(workout.date, workout.started_at, workout.id),
        )
        .options(selectinload(PerformedItem.sets))
    )
    return list(rows)


async def to_response(
    db: AsyncSession, user_id: uuid.UUID, workout: PerformedWorkout
) -> PerformedWorkoutResponse:
    items = list(workout.items)
    records: list[PersonalRecord] = []
    if workout.finished_at is not None:
        records = records_against(items, await _earlier_items(db, user_id, workout))
    return PerformedWorkoutResponse(
        id=workout.id,
        planned_id=workout.planned_id,
        date=workout.date,
        name=workout.name,
        note=workout.note,
        started_at=workout.started_at,
        finished_at=workout.finished_at,
        items=[PerformedItemResponse.model_validate(item) for item in items],
        summary=summarize(items).model_copy(update={"records": records}),
    )


def to_set(logged: SetLog) -> SetLogResponse:
    return SetLogResponse.model_validate(logged)


async def _lock(db: AsyncSession, key: str) -> None:
    """Один лог за раз: номера подходов и повторный старт не должны разъехаться."""
    await db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": key})


def _load_options():
    return selectinload(PerformedWorkout.items).selectinload(PerformedItem.sets)


async def get_performed(
    db: AsyncSession, user_id: uuid.UUID, performed_id: uuid.UUID
) -> PerformedWorkout | None:
    return await db.scalar(
        select(PerformedWorkout)
        .where(PerformedWorkout.id == performed_id, PerformedWorkout.user_id == user_id)
        .options(_load_options())
    )


async def _reload(
    db: AsyncSession, user_id: uuid.UUID, performed_id: uuid.UUID
) -> PerformedWorkout:
    db.expire_all()
    workout = await get_performed(db, user_id, performed_id)
    if workout is None:
        raise LogError("Тренировка не найдена")
    return workout


async def _performed_by_plan(
    db: AsyncSession, user_id: uuid.UUID, planned_id: uuid.UUID
) -> PerformedWorkout | None:
    return await db.scalar(
        select(PerformedWorkout)
        .where(PerformedWorkout.user_id == user_id, PerformedWorkout.planned_id == planned_id)
        .options(_load_options())
    )


def _apply_set(logged: SetLog, data: SetWrite) -> None:
    logged.weight = data.weight
    logged.extra_weight = data.extra_weight
    logged.reps = data.reps
    logged.rir = data.rir
    logged.is_warmup = data.is_warmup
    logged.is_assisted = data.is_assisted
    logged.is_negative = data.is_negative
    logged.note = data.note


async def _shift_positions(db: AsyncSession, sets: list[SetLog], index: int) -> None:
    """Сдвигает подходы начиная с index на одну позицию вправо, не нарушая уникальность."""
    for logged in sorted(sets, key=lambda item: item.position, reverse=True):
        if logged.position >= index:
            logged.position += 1000
    await db.flush()
    for logged in sets:
        if logged.position >= 1000:
            logged.position = logged.position - 1000 + 1
    await db.flush()


async def _renumber(db: AsyncSession, sets: list[SetLog]) -> None:
    ordered = sorted(sets, key=lambda item: item.position)
    for logged in ordered:
        logged.position += 1000
    await db.flush()
    for index, logged in enumerate(ordered):
        logged.position = index
    await db.flush()


def _snapshot_items(raw: list[dict[str, Any]]) -> list[PlanItemSnapshot]:
    return [PlanItemSnapshot.model_validate(item) for item in raw]


def _live_exercise_id(owned: Exercise | None) -> uuid.UUID | None:
    return None if owned is None else owned.id


async def start_from_plan(
    db: AsyncSession, user_id: uuid.UUID, planned_id: uuid.UUID
) -> tuple[PerformedWorkout, bool]:
    """Начинает тренировку из плана или возвращает уже начатую. День отдыха логом не становится."""
    await _lock(db, f"log-start:{planned_id}")
    existing = await _performed_by_plan(db, user_id, planned_id)
    if existing is not None:
        return existing, False

    # Тренировка блока без строки в базе сохраняется строкой, на которую ссылается лог.
    planned = await resolve_entry(db, user_id, planned_id)
    if planned is None:
        raise LogError("Запись плана не найдена")
    if planned.kind != KIND_WORKOUT:
        raise LogError("День отдыха нельзя записать как тренировку")

    workout = PerformedWorkout(
        user_id=user_id,
        planned_id=planned.id,
        date=planned.date,
        name=planned.name,
    )
    db.add(workout)
    await db.flush()

    for snapshot in _snapshot_items(list(planned.snapshot)):
        exercise = snapshot.exercise
        owned = await get_exercise(db, user_id, exercise.exercise_id)
        item = PerformedItem(
            performed_id=workout.id,
            position=snapshot.position,
            exercise_id=_live_exercise_id(owned),
            name=exercise.name,
            equipment=exercise.equipment,
            weight_type=exercise.weight_type,
            weight_unit=exercise.weight_unit,
            weight_step=exercise.weight_step,
            targets=[target.model_dump() for target in snapshot.sets],
        )
        db.add(item)
        await db.flush()
        for index, _target in enumerate(snapshot.sets):
            db.add(
                SetLog(
                    item_id=item.id,
                    performed_id=workout.id,
                    exercise_id=item.exercise_id,
                    position=index,
                )
            )
    await db.flush()
    return await _reload(db, user_id, workout.id), True


async def _require(
    db: AsyncSession, user_id: uuid.UUID, performed_id: uuid.UUID
) -> PerformedWorkout:
    workout = await get_performed(db, user_id, performed_id)
    if workout is None:
        raise LogError("Тренировка не найдена")
    return workout


def _item(workout: PerformedWorkout, item_id: uuid.UUID) -> PerformedItem:
    for item in workout.items:
        if item.id == item_id:
            return item
    raise LogError("Упражнение в тренировке не найдено")


def _set(workout: PerformedWorkout, set_id: uuid.UUID) -> SetLog:
    for item in workout.items:
        for logged in item.sets:
            if logged.id == set_id:
                return logged
    raise LogError("Подход не найден")


async def update_note(
    db: AsyncSession, user_id: uuid.UUID, performed_id: uuid.UUID, data: NoteWrite
) -> PerformedWorkout:
    workout = await _require(db, user_id, performed_id)
    workout.note = data.note
    await db.flush()
    return workout


async def update_item_note(
    db: AsyncSession,
    user_id: uuid.UUID,
    performed_id: uuid.UUID,
    item_id: uuid.UUID,
    data: NoteWrite,
) -> PerformedWorkout:
    workout = await _require(db, user_id, performed_id)
    _item(workout, item_id).note = data.note
    await db.flush()
    return workout


async def add_item(
    db: AsyncSession, user_id: uuid.UUID, performed_id: uuid.UUID, data: ItemCreate
) -> tuple[PerformedWorkout, bool]:
    await _lock(db, f"log:{performed_id}")
    workout = await _require(db, user_id, performed_id)
    if data.id is not None:
        for item in workout.items:
            if item.id == data.id:
                return workout, False
    if len(workout.items) >= MAX_ITEMS:
        raise LogError("В тренировке уже максимум упражнений")
    exercise = await get_exercise(db, user_id, data.exercise_id)
    if exercise is None:
        raise LogError("Упражнение не найдено в вашем справочнике")
    item = PerformedItem(
        id=data.id or uuid.uuid4(),
        performed_id=workout.id,
        position=len(workout.items),
        exercise_id=exercise.id,
        name=exercise.name,
        equipment=exercise.equipment,
        weight_type=exercise.weight_type,
        weight_unit=exercise.weight_unit,
        weight_step=exercise.weight_step,
        targets=[],
    )
    db.add(item)
    await db.flush()
    db.add(
        SetLog(
            id=data.set_id or uuid.uuid4(),
            item_id=item.id,
            performed_id=workout.id,
            exercise_id=exercise.id,
            position=0,
        )
    )
    await db.flush()
    return await _reload(db, user_id, workout.id), True


async def replace_exercise(
    db: AsyncSession,
    user_id: uuid.UUID,
    performed_id: uuid.UUID,
    item_id: uuid.UUID,
    data: ExerciseReplace,
) -> PerformedWorkout:
    workout = await _require(db, user_id, performed_id)
    item = _item(workout, item_id)
    exercise = await get_exercise(db, user_id, data.exercise_id)
    if exercise is None:
        raise LogError("Упражнение не найдено в вашем справочнике")
    item.exercise_id = exercise.id
    item.name = exercise.name
    item.equipment = exercise.equipment
    item.weight_type = exercise.weight_type
    item.weight_unit = exercise.weight_unit
    item.weight_step = exercise.weight_step
    item.targets = []
    for logged in item.sets:
        logged.exercise_id = exercise.id
    await db.flush()
    return await _reload(db, user_id, workout.id)


async def add_set(
    db: AsyncSession,
    user_id: uuid.UUID,
    performed_id: uuid.UUID,
    item_id: uuid.UUID,
    data: SetCreate,
) -> tuple[SetLog, bool]:
    await _lock(db, f"log:{performed_id}")
    workout = await _require(db, user_id, performed_id)
    if data.id is not None:
        for item in workout.items:
            for logged in item.sets:
                if logged.id == data.id:
                    return logged, False
    item = _item(workout, item_id)
    if len(item.sets) >= MAX_SETS:
        raise LogError("У упражнения уже максимум подходов")
    index = len(item.sets) if data.position is None else min(data.position, len(item.sets))
    await _shift_positions(db, list(item.sets), index)
    logged = SetLog(
        id=data.id or uuid.uuid4(),
        item_id=item.id,
        performed_id=workout.id,
        exercise_id=item.exercise_id,
        position=index,
    )
    _apply_set(logged, data)
    db.add(logged)
    await db.flush()
    return logged, True


async def update_set(
    db: AsyncSession,
    user_id: uuid.UUID,
    performed_id: uuid.UUID,
    set_id: uuid.UUID,
    data: SetWrite,
) -> SetLog:
    workout = await _require(db, user_id, performed_id)
    logged = _set(workout, set_id)
    _apply_set(logged, data)
    await db.flush()
    return logged


async def delete_set(
    db: AsyncSession, user_id: uuid.UUID, performed_id: uuid.UUID, set_id: uuid.UUID
) -> PerformedWorkout:
    await _lock(db, f"log:{performed_id}")
    workout = await _require(db, user_id, performed_id)
    logged = _set(workout, set_id)
    item = _item(workout, logged.item_id)
    await db.delete(logged)
    await db.flush()
    remaining = [candidate for candidate in item.sets if candidate.id != set_id]
    await _renumber(db, remaining)
    return await _reload(db, user_id, workout.id)


async def finish(db: AsyncSession, user_id: uuid.UUID, performed_id: uuid.UUID) -> PerformedWorkout:
    """Ставит время окончания. Запланированную тренировку отмечает выполненной."""
    workout = await _require(db, user_id, performed_id)
    workout.finished_at = datetime.now(UTC)
    if workout.planned_id is not None:
        planned = await db.scalar(
            select(PlannedWorkout).where(
                PlannedWorkout.id == workout.planned_id, PlannedWorkout.user_id == user_id
            )
        )
        if planned is not None and planned.status == STATUS_PLANNED:
            planned.status = STATUS_DONE
    await db.flush()
    return workout


async def previous_sets(
    db: AsyncSession,
    user_id: uuid.UUID,
    exercise_id: uuid.UUID,
    *,
    exclude_id: uuid.UUID | None,
) -> PreviousSets | None:
    """Последняя другая тренировка с этим упражнением. Текущая сессия не входит."""
    exercise = await get_exercise(db, user_id, exercise_id)
    if exercise is None:
        raise LogError("Упражнение не найдено в вашем справочнике")
    query = (
        select(PerformedItem, PerformedWorkout)
        .join(PerformedWorkout, PerformedItem.performed_id == PerformedWorkout.id)
        .where(
            PerformedWorkout.user_id == user_id,
            PerformedItem.exercise_id == exercise_id,
        )
        .order_by(
            PerformedWorkout.date.desc(),
            PerformedWorkout.started_at.desc(),
            PerformedItem.position.desc(),
        )
        .options(selectinload(PerformedItem.sets))
    )
    if exclude_id is not None:
        query = query.where(PerformedWorkout.id != exclude_id)
    query = query.limit(1)
    row = (await db.execute(query)).first()
    if row is None:
        return None
    item, workout = row
    return PreviousSets(
        performed_id=workout.id,
        date=workout.date,
        sets=[SetLogResponse.model_validate(logged) for logged in item.sets],
    )
