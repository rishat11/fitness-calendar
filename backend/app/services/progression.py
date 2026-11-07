"""Двойная прогрессия: чистый расчёт и то же решение в API.

`progression_hint` не читает базу. Чтение подсказки и принятие вызывают её
с одним и тем же списком сессий. Подсказка не переписывает шаблон и план.
«Принять» для повышения веса только подставляет предлагаемый вес в следующий
пустой рабочий подход открытого лога.

Сессии сравниваются внутри одного типа недели. Тип берётся у последней
сессии с рабочими подходами: многоповторка не смешивается с гипертрофией.
Сессии без типа (тренировка вне блока) сравниваются только между собой —
так же, как до периодизации. Разгрузка не базовая точка повышения веса:
если последняя сессия разгрузочная и на верхней границе повторов, прибавку
к её весу не предлагаем.
"""

import datetime as dt
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.block import WEEK_TYPES, BlockPlacement
from app.models.log import PerformedItem, PerformedWorkout, SetLog
from app.models.plan import PlannedWorkout
from app.models.progression import ProgressionDecision
from app.services.block_rules import DAYS_IN_WEEK
from app.services.exercises import get_exercise
from app.services.log import get_performed, set_load

STATUS_INCREASE = "increase_weight"
STATUS_CONTINUE = "continue"
STATUS_STAGNATION = "stagnation"

HintStatus = Literal["increase_weight", "continue", "stagnation"]

MESSAGE_INCREASE = (
    "Повысьте вес на шаг упражнения. После повышения ожидаются повторы около нижней границы."
)
MESSAGE_CONTINUE = "Продолжайте, добавляйте повторы."
MESSAGE_STAGNATION = (
    "Проверьте сон и питание, уменьшите вес на 5–10%, рассмотрите разгрузку или замену упражнения."
)

# Верхняя граница поля веса в логе. Выше этого «принять» нечего записывать.
MAX_SET_WEIGHT = 2000


class ProgressionError(Exception):
    """Подсказку нельзя показать или решение нельзя записать."""

    def __init__(self, message: str, *, missing: bool = False) -> None:
        super().__init__(message)
        self.missing = missing


@dataclass(frozen=True, slots=True)
class TargetInput:
    rep_min: int
    rep_max: int
    target_rir: int | None


@dataclass(frozen=True, slots=True)
class SetInput:
    position: int
    weight: float | None
    extra_weight: float | None
    reps: int | None
    rir: int | None
    is_warmup: bool
    is_assisted: bool
    is_negative: bool
    weight_type: str
    weight_step: float
    weight_unit: str


# Как у `BlockWeek.week_type`. None — тренировка вне блока.
WeekKind = Literal["high_reps", "hypertrophy", "strength", "deload", "free"]


@dataclass(frozen=True, slots=True)
class SessionInput:
    """Одна тренировка, в которой упражнение уже встречалось. Дата без часового пояса."""

    id: uuid.UUID
    date: dt.date
    started_at: dt.datetime
    targets: tuple[TargetInput, ...]
    sets: tuple[SetInput, ...]
    # None — вне блока: такие сессии сравниваются между собой, без недель блока.
    week_type: WeekKind | None = None


@dataclass(frozen=True, slots=True)
class SessionBest:
    load: float | None
    reps: int
    epley_1rm: float | None


@dataclass(frozen=True, slots=True)
class ProgressionHint:
    status: HintStatus
    message: str
    suggested_weight: float | None
    weight_unit: str | None
    last_session_id: uuid.UUID
    epley_1rm: float | None
    # Тип недели, внутри которого посчитана подсказка. None — тренировки вне блока.
    week_type: WeekKind | None


@dataclass(frozen=True, slots=True)
class DecisionOutcome:
    action: str
    performed_id: uuid.UUID | None
    set_id: uuid.UUID | None
    weight: float | None


def decision_fingerprint(
    status: str, last_session_id: uuid.UUID, suggested_weight: float | None
) -> str:
    """Отпечаток входов: статус, последняя сессия и предлагаемый вес."""
    if suggested_weight is None:
        weight = ""
    else:
        weight = f"{round(suggested_weight, 2):.2f}"
    return f"{status}:{last_session_id}:{weight}"


def _load(logged: SetInput) -> float | None:
    value = set_load(logged.weight_type, logged.weight, logged.extra_weight)
    if value is None:
        return None
    return round(value, 4)


def qualifying_sets(sets: Sequence[SetInput]) -> list[SetInput]:
    """Рабочий подход: не разминка, не «с помощью», не негативы, заполнены вес и повторы."""
    rows = [
        logged
        for logged in sets
        if not logged.is_warmup
        and not logged.is_assisted
        and not logged.is_negative
        and logged.weight is not None
        and logged.reps is not None
    ]
    return sorted(rows, key=lambda logged: logged.position)


def _qualifying(session: SessionInput) -> list[SetInput]:
    return qualifying_sets(session.sets)


def _target_for(
    index: int,
    targets: tuple[TargetInput, ...],
    catalog_rep_min: int,
    catalog_rep_max: int,
) -> tuple[int, int, int | None]:
    if not targets:
        return catalog_rep_min, catalog_rep_max, None
    target = targets[index] if index < len(targets) else targets[-1]
    return target.rep_min, target.rep_max, target.target_rir


def _rir_reached(actual: int | None, target: int | None) -> bool:
    if target is None:
        return True
    if actual is None:
        return False
    return actual >= target


def _at_top(
    sets: Sequence[SetInput],
    targets: tuple[TargetInput, ...],
    catalog_rep_min: int,
    catalog_rep_max: int,
) -> bool:
    for index, logged in enumerate(sets):
        _, rep_max, target_rir = _target_for(index, targets, catalog_rep_min, catalog_rep_max)
        if (logged.reps or 0) < rep_max or not _rir_reached(logged.rir, target_rir):
            return False
    return True


def _winner(sets: Sequence[SetInput]) -> SetInput:
    def sort_key(logged: SetInput) -> tuple[bool, float, int]:
        load = _load(logged)
        return (load is not None, load if load is not None else 0.0, logged.reps or 0)

    return max(sets, key=sort_key)


def _best(sets: Sequence[SetInput]) -> SessionBest:
    winner = _winner(sets)
    load = _load(winner)
    reps = winner.reps or 0
    # Формула Эпли. Для гравитрона нагрузки нет, поэтому 1ПМ не считается.
    epley = None if load is None else round(load * (1 + reps / 30), 2)
    return SessionBest(load=load, reps=reps, epley_1rm=epley)


def best_working_point(sets: Sequence[SetInput]) -> tuple[SetInput, SessionBest] | None:
    """Лучший рабочий подход сессии. Те же отборы, что у подсказки прогрессии.

    Возвращает сам подход и его нагрузку, повторы и расчётный 1ПМ.
    Пустой список и сессия только из разминки, помощи или негативов дают None.
    """
    rows = qualifying_sets(sets)
    if not rows:
        return None
    winner = _winner(rows)
    return winner, _best(rows)


def _suggested_weight(logged: SetInput) -> float | None:
    """Число для поля веса: нагрузка последнего рабочего подхода плюс шаг.

    Для гантелей поле — вес одной гантели, а нагрузка вдвое больше, поэтому
    в поле пишется половина новой нагрузки. Гравитрон нагрузки не даёт.
    """
    load = _load(logged)
    if load is None:
        return None
    new_load = round(load + logged.weight_step, 2)
    if logged.weight_type == "per_dumbbell":
        return round(new_load / 2, 2)
    return new_load


def _better(later: SessionBest, earlier: SessionBest) -> bool:
    if later.load is None or earlier.load is None:
        if later.load is None and earlier.load is None:
            return later.reps > earlier.reps
        return False
    if later.load > earlier.load:
        return True
    return later.load == earlier.load and later.reps > earlier.reps


def _fell(later: SessionBest, earlier: SessionBest) -> bool:
    if later.load is None or earlier.load is None:
        return False
    return later.load < earlier.load and later.reps < earlier.reps


def _make(
    status: HintStatus,
    message: str,
    session: SessionInput,
    best: SessionBest,
    *,
    suggested_weight: float | None,
    weight_unit: str | None,
) -> ProgressionHint:
    return ProgressionHint(
        status=status,
        message=message,
        suggested_weight=suggested_weight,
        weight_unit=weight_unit,
        last_session_id=session.id,
        epley_1rm=best.epley_1rm,
        week_type=session.week_type,
    )


def _prepare(
    sessions: Sequence[SessionInput],
) -> list[tuple[SessionInput, list[SetInput], SessionBest]]:
    prepared: list[tuple[SessionInput, list[SetInput], SessionBest]] = []
    ordered = sorted(sessions, key=lambda session: (session.date, session.started_at, session.id))
    for session in ordered:
        sets = _qualifying(session)
        if not sets:
            continue
        prepared.append((session, sets, _best(sets)))
    return prepared


def _hint_for(
    prepared: Sequence[tuple[SessionInput, list[SetInput], SessionBest]],
    *,
    catalog_rep_min: int,
    catalog_rep_max: int,
) -> ProgressionHint | None:
    """Решение по уже отобранной группе одного типа. Группа не пустая."""
    session, sets, best = prepared[-1]
    last = sets[-1]
    unit = last.weight_unit
    suggested = _suggested_weight(last)
    at_top = suggested is not None and _at_top(
        sets, session.targets, catalog_rep_min, catalog_rep_max
    )
    # Разгрузка на верхней границе не задаёт вес следующей прибавки. «Продолжайте»
    # здесь тоже не подходит: повторы уже у верхней границы.
    if at_top and session.week_type == "deload":
        return None
    if at_top:
        return _make(
            STATUS_INCREASE,
            MESSAGE_INCREASE,
            session,
            best,
            suggested_weight=suggested,
            weight_unit=unit,
        )
    if len(prepared) >= 2 and _better(best, prepared[-2][2]):
        return _make(
            STATUS_CONTINUE,
            MESSAGE_CONTINUE,
            session,
            best,
            suggested_weight=None,
            weight_unit=unit,
        )
    if len(prepared) >= 3:
        recent = prepared[-3:]
        earlier, middle, latest = recent
        no_progress = not _better(middle[2], earlier[2]) and not _better(latest[2], middle[2])
        if no_progress or _fell(latest[2], middle[2]):
            return _make(
                STATUS_STAGNATION,
                MESSAGE_STAGNATION,
                session,
                best,
                suggested_weight=None,
                weight_unit=unit,
            )
    return None


def progression_hint(
    sessions: Sequence[SessionInput],
    *,
    catalog_rep_min: int,
    catalog_rep_max: int,
) -> ProgressionHint | None:
    """Статус последней сессии своего типа. Сессия — тренировка с рабочим подходом.

    Порядок сессий: дата, затем время начала. Пустые подходы игнорируются.
    Сравнение идёт только с сессиями того же `week_type`, что у последней.
    `None` — отдельная группа: тренировки вне блока, прежнее правило.
    Диапазон и целевой RIR берутся из снимка сессии; пустой снимок — из справочника.
    Если целевой RIR нигде не задан, условие по RIR выполнено.
    """
    prepared = _prepare(sessions)
    if not prepared:
        return None
    week_type = prepared[-1][0].week_type
    group = [row for row in prepared if row[0].week_type == week_type]
    return _hint_for(group, catalog_rep_min=catalog_rep_min, catalog_rep_max=catalog_rep_max)


def week_type_for_offset(
    day_offset: int | None, weeks: Sequence[Mapping[str, object]] | None
) -> WeekKind | None:
    """Тип недели блока по номеру дня от старта размещения.

    Индекс тот же, что у слотов календаря: `day_offset // 7`. Нет снимка,
    день вне блока или неизвестный тип — тренировка без типа.
    """
    if day_offset is None or day_offset < 0 or not weeks:
        return None
    index = day_offset // DAYS_IN_WEEK
    if index >= len(weeks):
        return None
    week = weeks[index]
    raw = week.get("week_type")
    if not isinstance(raw, str) or raw not in WEEK_TYPES:
        return None
    return raw  # type: ignore[return-value]


def _parse_targets(raw: list[dict[str, int | None]]) -> tuple[TargetInput, ...]:
    parsed: list[TargetInput] = []
    for row in raw:
        rep_min = row.get("rep_min")
        rep_max = row.get("rep_max")
        if not isinstance(rep_min, int) or not isinstance(rep_max, int):
            continue
        target_rir = row.get("target_rir")
        parsed.append(
            TargetInput(
                rep_min=rep_min,
                rep_max=rep_max,
                target_rir=target_rir if isinstance(target_rir, int) else None,
            )
        )
    return tuple(parsed)


def _session_from(
    workout: PerformedWorkout, exercise_id: uuid.UUID, week_type: WeekKind | None = None
) -> SessionInput | None:
    items = sorted(
        (item for item in workout.items if item.exercise_id == exercise_id),
        key=lambda item: item.position,
    )
    if not items:
        return None
    targets: list[TargetInput] = []
    sets: list[SetInput] = []
    position = 0
    for item in items:
        targets.extend(_parse_targets(item.targets))
        for logged in sorted(item.sets, key=lambda row: row.position):
            sets.append(
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
    return SessionInput(
        id=workout.id,
        date=workout.date,
        started_at=workout.started_at,
        targets=tuple(targets),
        sets=tuple(sets),
        week_type=week_type,
    )


async def _week_types(
    db: AsyncSession, user_id: uuid.UUID, workout_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, WeekKind]:
    """Тип недели факта: план блока → номер дня → снимок недель размещения."""
    if not workout_ids:
        return {}
    rows = await db.execute(
        select(PerformedWorkout.id, PlannedWorkout.day_offset, BlockPlacement.weeks_snapshot)
        .join(PlannedWorkout, PlannedWorkout.id == PerformedWorkout.planned_id)
        .join(BlockPlacement, BlockPlacement.id == PlannedWorkout.placement_id)
        .where(
            PerformedWorkout.user_id == user_id,
            PerformedWorkout.id.in_(workout_ids),
            PlannedWorkout.user_id == user_id,
            BlockPlacement.user_id == user_id,
        )
    )
    found: dict[uuid.UUID, WeekKind] = {}
    for performed_id, day_offset, weeks in rows.all():
        week_type = week_type_for_offset(day_offset, weeks)
        if week_type is not None:
            found[performed_id] = week_type
    return found


async def _sessions(
    db: AsyncSession, user_id: uuid.UUID, exercise_id: uuid.UUID
) -> list[SessionInput]:
    workouts = list(
        await db.scalars(
            select(PerformedWorkout)
            .where(
                PerformedWorkout.user_id == user_id,
                PerformedWorkout.items.any(PerformedItem.exercise_id == exercise_id),
            )
            .options(selectinload(PerformedWorkout.items).selectinload(PerformedItem.sets))
        )
    )
    types = await _week_types(db, user_id, [workout.id for workout in workouts])
    sessions: list[SessionInput] = []
    for workout in workouts:
        session = _session_from(workout, exercise_id, types.get(workout.id))
        if session is not None:
            sessions.append(session)
    return sessions


async def _stored_decision(
    db: AsyncSession, user_id: uuid.UUID, exercise_id: uuid.UUID, fingerprint: str
) -> ProgressionDecision | None:
    return await db.scalar(
        select(ProgressionDecision).where(
            ProgressionDecision.user_id == user_id,
            ProgressionDecision.exercise_id == exercise_id,
            ProgressionDecision.fingerprint == fingerprint,
        )
    )


async def compute_hint(
    db: AsyncSession, user_id: uuid.UUID, exercise_id: uuid.UUID
) -> ProgressionHint | None:
    """Считает подсказку. None — упражнения нет у пользователя (missing) или считать не из чего."""
    exercise = await get_exercise(db, user_id, exercise_id)
    if exercise is None:
        raise ProgressionError("Упражнение не найдено", missing=True)
    sessions = await _sessions(db, user_id, exercise_id)
    return progression_hint(
        sessions, catalog_rep_min=exercise.rep_min, catalog_rep_max=exercise.rep_max
    )


async def visible_hint(
    db: AsyncSession, user_id: uuid.UUID, exercise_id: uuid.UUID
) -> ProgressionHint | None:
    hint = await compute_hint(db, user_id, exercise_id)
    if hint is None:
        return None
    fingerprint = decision_fingerprint(hint.status, hint.last_session_id, hint.suggested_weight)
    decision = await _stored_decision(db, user_id, exercise_id, fingerprint)
    if decision is not None:
        return None
    return hint


def _is_open_working_slot(logged: SetLog) -> bool:
    return (
        not logged.is_warmup
        and not logged.is_assisted
        and not logged.is_negative
        and logged.weight is None
    )


async def _next_empty_set(
    db: AsyncSession,
    user_id: uuid.UUID,
    exercise_id: uuid.UUID,
    performed_id: uuid.UUID | None,
) -> SetLog | None:
    stmt = (
        select(PerformedWorkout)
        .where(
            PerformedWorkout.user_id == user_id,
            PerformedWorkout.finished_at.is_(None),
            PerformedWorkout.items.any(PerformedItem.exercise_id == exercise_id),
        )
        .options(selectinload(PerformedWorkout.items).selectinload(PerformedItem.sets))
        .order_by(
            PerformedWorkout.date.desc(),
            PerformedWorkout.started_at.desc(),
            PerformedWorkout.id.desc(),
        )
    )
    if performed_id is not None:
        stmt = stmt.where(PerformedWorkout.id == performed_id)
    workouts = list(await db.scalars(stmt))
    for workout in workouts:
        items = sorted(
            (item for item in workout.items if item.exercise_id == exercise_id),
            key=lambda item: item.position,
        )
        for item in items:
            for logged in sorted(item.sets, key=lambda row: row.position):
                if _is_open_working_slot(logged):
                    return logged
    return None


async def decide(
    db: AsyncSession,
    user_id: uuid.UUID,
    exercise_id: uuid.UUID,
    action: str,
    *,
    performed_id: uuid.UUID | None,
) -> DecisionOutcome:
    hint = await compute_hint(db, user_id, exercise_id)
    if hint is None:
        raise ProgressionError("Подсказки для этого упражнения нет")
    fingerprint = decision_fingerprint(hint.status, hint.last_session_id, hint.suggested_weight)
    if await _stored_decision(db, user_id, exercise_id, fingerprint) is not None:
        raise ProgressionError("Эта подсказка уже решена")

    filled: SetLog | None = None
    if action == "accept" and hint.status == STATUS_INCREASE:
        if performed_id is not None and await get_performed(db, user_id, performed_id) is None:
            raise ProgressionError("Тренировка не найдена", missing=True)
        filled = await _next_empty_set(db, user_id, exercise_id, performed_id)
        if filled is None or hint.suggested_weight is None:
            raise ProgressionError(
                "Нет открытой тренировки с пустым рабочим подходом этого упражнения"
            )
        if not 0 <= hint.suggested_weight <= MAX_SET_WEIGHT:
            raise ProgressionError("Предлагаемый вес нельзя записать в подход")
        filled.weight = hint.suggested_weight

    db.add(
        ProgressionDecision(
            user_id=user_id,
            exercise_id=exercise_id,
            status=hint.status,
            last_session_id=hint.last_session_id,
            suggested_weight=hint.suggested_weight,
            fingerprint=fingerprint,
            action=action,
        )
    )
    await db.flush()
    return DecisionOutcome(
        action=action,
        performed_id=None if filled is None else filled.performed_id,
        set_id=None if filled is None else filled.id,
        weight=None if filled is None else filled.weight,
    )
