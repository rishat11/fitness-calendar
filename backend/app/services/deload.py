"""Разгрузка: неделя по умолчанию и предложение сделать её раньше плана.

`suggest_early_deload` и `with_default_deload` не читают базу и ничего не записывают.
Чтение подсказки вызывает расчёт и отдаёт ответ. Принятие — отдельное действие:
оно меняет снимок недели размещения, а не библиотеку блоков.
"""

import datetime as dt
import uuid
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.block import MAX_BLOCK_WEEKS, BlockPlacement
from app.models.log import PerformedItem, PerformedWorkout
from app.models.plan import STATUS_PLANNED, STATUS_SKIPPED, PlannedWorkout
from app.services.block_rules import DAYS_IN_WEEK, apply_week

# Середина диапазона spec 4.7 — «50–60% объёма». 0.5 ровно половина подходов.
DEFAULT_DELOAD_VOLUME = 0.5
# Верх запаса «3–4»: разгрузка легче обычной недели с целевым RIR 1–2.
DEFAULT_DELOAD_RIR = 4

# Сколько независимых признаков нужно, чтобы предложить разгрузку.
SIGNS_REQUIRED = 2
# RIR 0 или 1 — подход у отказа или в одном повторе от него.
LOW_RIR_MAX = 1
LOW_RIR_EXERCISES = 2
# Падение лучших повторов упражнения относительно предыдущей тренировочной недели.
REP_DROP_MIN = 2
REP_DROP_EXERCISES = 2
# Нет роста повторов столько тренировочных недель подряд.
STAGNATION_WEEKS = 3
STAGNATION_EXERCISES = 2
# Пропуски суммируются по последним календарным неделям истории.
SKIP_SESSIONS = 2
SKIP_WINDOW_WEEKS = 2
# Самочувствие по шкале 1–5. 1 и 2 — низкое. Вне шкалы значение игнорируется.
WELLBEING_SCALE_MIN = 1
WELLBEING_SCALE_MAX = 5
WELLBEING_LOW_MAX = 2

REASON_LOW_RIR = "low_rir"
REASON_REP_DROP = "rep_drop"
REASON_SKIPS = "skips"
REASON_STAGNATION = "stagnation"
REASON_LOW_WELLBEING = "low_wellbeing"

REASON_TEXT = {
    REASON_LOW_RIR: "В последней тренировочной неделе RIR 0–1 у двух и более упражнений.",
    REASON_REP_DROP: "Повторы упали минимум на 2 у двух и более упражнений.",
    REASON_SKIPS: "За последние две недели пропущено две или больше тренировок.",
    REASON_STAGNATION: "Три недели подряд нет роста повторов у двух и более упражнений.",
    REASON_LOW_WELLBEING: "Низкая оценка самочувствия.",
}

MESSAGE_OUTSIDE = "Сейчас блок не идёт, разгружать нечего."
MESSAGE_ALREADY = "Эта неделя уже разгрузочная."
MESSAGE_QUIET = "Признаков усталости пока недостаточно, чтобы разгрузиться раньше плана."
MESSAGE_SUGGEST = "Есть признаки усталости. Эту неделю можно сделать разгрузкой раньше плана."


class DeloadRoomError(Exception):
    """В блоке нет места для недели разгрузки, а своей разгрузки пользователь не указал."""


class DeloadError(Exception):
    """Подсказку нельзя показать или разгрузку нельзя принять."""

    def __init__(self, message: str, *, missing: bool = False) -> None:
        super().__init__(message)
        self.missing = missing


@dataclass(frozen=True, slots=True)
class WeekSpec:
    """Параметры недели, с которыми работает и библиотека, и снимок размещения."""

    week_type: str
    rep_min: int
    rep_max: int
    target_rir: int
    volume_multiplier: float


@dataclass(frozen=True, slots=True)
class ExerciseWeek:
    """Лучшие рабочие повторы и ближайший к отказу RIR упражнения за неделю."""

    exercise_id: uuid.UUID
    reps: int | None
    rir: int | None


@dataclass(frozen=True, slots=True)
class WeekRecord:
    """Одна календарная неделя. Пустую неделю тоже передают, чтобы не сдвинуть окно пропусков.

    `skipped` — число пропущенных тренировок за эту неделю.
    `wellbeing` — оценка самочувствия 1–5 или None, если оценки нет.
    """

    exercises: tuple[ExerciseWeek, ...] = ()
    skipped: int = 0
    wellbeing: int | None = None


@dataclass(frozen=True, slots=True)
class DeloadSuggestion:
    """Решение расчёта. `needed` само по себе план не меняет."""

    needed: bool
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SuggestionView:
    suggest: bool
    placement_id: uuid.UUID
    week_position: int | None
    message: str
    reasons: tuple[tuple[str, str], ...]


@dataclass(frozen=True, slots=True)
class AcceptResult:
    placement_id: uuid.UUID
    week_position: int
    volume_multiplier: float
    target_rir: int


def with_default_deload(weeks: Sequence[WeekSpec]) -> list[WeekSpec]:
    """Добавляет неделю разгрузки, если в блоке её ещё нет.

    Объём — `DEFAULT_DELOAD_VOLUME` (0.5, нижняя граница 50–60% из spec 4.7).
    Целевой RIR — `DEFAULT_DELOAD_RIR` (4, верх запаса 3–4). Диапазон повторов
    копируется с последней недели. Уже указанную разгрузку функция не трогает:
    множитель и запас остаются такими, как задал пользователь.
    Блок из `MAX_BLOCK_WEEKS` недель без разгрузки не ужимается — тогда
    поднимается `DeloadRoomError`.
    """
    if any(week.week_type == "deload" for week in weeks):
        return list(weeks)
    if len(weeks) >= MAX_BLOCK_WEEKS:
        raise DeloadRoomError(
            f"В блоке уже {MAX_BLOCK_WEEKS} недель без разгрузки. "
            "Уберите одну неделю или отметьте неделю как разгрузку."
        )
    source = weeks[-1]
    return [
        *weeks,
        WeekSpec(
            week_type="deload",
            rep_min=source.rep_min,
            rep_max=source.rep_max,
            target_rir=DEFAULT_DELOAD_RIR,
            volume_multiplier=DEFAULT_DELOAD_VOLUME,
        ),
    ]


def _prefer_max(left: int | None, right: int | None) -> int | None:
    if left is None:
        return right
    if right is None:
        return left
    return max(left, right)


def _prefer_min(left: int | None, right: int | None) -> int | None:
    if left is None:
        return right
    if right is None:
        return left
    return min(left, right)


def _exercise_map(week: WeekRecord) -> dict[uuid.UUID, ExerciseWeek]:
    """Одно упражнение за неделю: лучшие повторы и минимальный RIR."""
    merged: dict[uuid.UUID, ExerciseWeek] = {}
    for point in week.exercises:
        previous = merged.get(point.exercise_id)
        if previous is None:
            merged[point.exercise_id] = point
            continue
        merged[point.exercise_id] = ExerciseWeek(
            point.exercise_id,
            _prefer_max(previous.reps, point.reps),
            _prefer_min(previous.rir, point.rir),
        )
    return merged


def _has_training(week: WeekRecord) -> bool:
    return any(point.reps is not None or point.rir is not None for point in week.exercises)


def _low_rir(latest: WeekRecord) -> bool:
    close_to_failure = sum(
        1
        for point in _exercise_map(latest).values()
        if point.rir is not None and point.rir <= LOW_RIR_MAX
    )
    return close_to_failure >= LOW_RIR_EXERCISES


def _rep_drop(previous: WeekRecord, latest: WeekRecord) -> bool:
    before = _exercise_map(previous)
    drops = 0
    for exercise_id, point in _exercise_map(latest).items():
        earlier = before.get(exercise_id)
        if earlier is None or earlier.reps is None or point.reps is None:
            continue
        if earlier.reps - point.reps >= REP_DROP_MIN:
            drops += 1
    return drops >= REP_DROP_EXERCISES


def _stagnation(trained: Sequence[WeekRecord]) -> bool:
    if len(trained) < STAGNATION_WEEKS:
        return False
    window = trained[-STAGNATION_WEEKS:]
    maps = [_exercise_map(week) for week in window]
    stalled = 0
    for exercise_id, last in maps[-1].items():
        series = [item.get(exercise_id) for item in maps]
        reps = [item.reps if item is not None else None for item in series]
        if any(value is None for value in reps) or last.reps is None:
            continue
        # Нет роста: каждый следующий результат не выше предыдущего.
        if reps[1] <= reps[0] and reps[2] <= reps[1]:
            stalled += 1
    return stalled >= STAGNATION_EXERCISES


def _skips(weeks: Sequence[WeekRecord]) -> bool:
    window = weeks[-SKIP_WINDOW_WEEKS:]
    return sum(max(week.skipped, 0) for week in window) >= SKIP_SESSIONS


def _low_wellbeing(week: WeekRecord) -> bool:
    score = week.wellbeing
    if score is None or score < WELLBEING_SCALE_MIN or score > WELLBEING_SCALE_MAX:
        return False
    return score <= WELLBEING_LOW_MAX


def suggest_early_deload(weeks: Sequence[WeekRecord], *, target_week_type: str) -> DeloadSuggestion:
    """Нужна ли разгрузка раньше плана.

    История идёт от старой недели к новой, по одной записи на календарную неделю.
    Признаки считаются независимо, предложение появляется от `SIGNS_REQUIRED` (2):

    - `low_rir` — в последней неделе, где есть подходы, минимум у `LOW_RIR_EXERCISES`
      упражнений минимальный RIR не выше `LOW_RIR_MAX` (0–1);
    - `rep_drop` — лучшие повторы упали минимум на `REP_DROP_MIN` у
      `REP_DROP_EXERCISES` упражнений относительно предыдущей тренировочной недели;
    - `skips` — за последние `SKIP_WINDOW_WEEKS` календарные недели суммарно
      не меньше `SKIP_SESSIONS` пропусков;
    - `stagnation` — у `STAGNATION_EXERCISES` упражнений повторы не выросли
      `STAGNATION_WEEKS` тренировочные недели подряд;
    - `low_wellbeing` — у последней календарной недели оценка самочувствия
      от 1 до `WELLBEING_LOW_MAX` по шкале 1–5. None и числа вне шкалы признаком не являются.

    Пустые недели не участвуют в сравнении повторов и RIR, но входят в окно пропусков.
    Если `target_week_type` уже `deload`, `needed` ложно: разгрузка на эту неделю
    и так стоит, раньше срока её предлагать не нужно. Причины при этом сохраняются.
    Функция только считает решение и ничего не меняет.
    """
    trained = [week for week in weeks if _has_training(week)]
    reasons: list[str] = []
    if trained and _low_rir(trained[-1]):
        reasons.append(REASON_LOW_RIR)
    if len(trained) >= 2 and _rep_drop(trained[-2], trained[-1]):
        reasons.append(REASON_REP_DROP)
    if weeks and _skips(weeks):
        reasons.append(REASON_SKIPS)
    if _stagnation(trained):
        reasons.append(REASON_STAGNATION)
    if weeks and _low_wellbeing(weeks[-1]):
        reasons.append(REASON_LOW_WELLBEING)

    needed = target_week_type != "deload" and len(reasons) >= SIGNS_REQUIRED
    return DeloadSuggestion(needed=needed, reasons=tuple(reasons))


def _target_index(placement: BlockPlacement, today: dt.date) -> int | None:
    if today < placement.start_date or today > placement.end_date:
        return None
    index = (today - placement.start_date).days // DAYS_IN_WEEK
    if index < 0 or index >= len(placement.weeks_snapshot):
        return None
    return index


def _merge_point(
    bucket: dict[uuid.UUID, tuple[int | None, int | None]],
    exercise_id: uuid.UUID,
    reps: int | None,
    rir: int | None,
) -> None:
    previous = bucket.get(exercise_id)
    if previous is None:
        bucket[exercise_id] = (reps, rir)
        return
    bucket[exercise_id] = (_prefer_max(previous[0], reps), _prefer_min(previous[1], rir))


async def _week_records(
    db: AsyncSession, user_id: uuid.UUID, placement: BlockPlacement, today: dt.date
) -> list[WeekRecord]:
    """Недели размещения от старта до текущей включительно.

    Повторы и RIR берутся из рабочих подходов (разминка не считается). Пропуск —
    тренировка этого размещения со статусом «пропущена». Оценки самочувствия
    в данных пока нет, поэтому у недель она пустая.
    """
    index = _target_index(placement, today)
    if index is None:
        return []
    start = placement.start_date
    through = min(placement.end_date, start + dt.timedelta(days=(index + 1) * DAYS_IN_WEEK - 1))
    workouts = list(
        await db.scalars(
            select(PerformedWorkout)
            .where(
                PerformedWorkout.user_id == user_id,
                PerformedWorkout.date >= start,
                PerformedWorkout.date <= through,
            )
            .options(selectinload(PerformedWorkout.items).selectinload(PerformedItem.sets))
        )
    )
    points: dict[int, dict[uuid.UUID, tuple[int | None, int | None]]] = {}
    for workout in workouts:
        week_index = (workout.date - start).days // DAYS_IN_WEEK
        if week_index < 0 or week_index > index:
            continue
        bucket = points.setdefault(week_index, {})
        for item in workout.items:
            for logged in item.sets:
                if logged.is_warmup or logged.exercise_id is None:
                    continue
                if logged.reps is None and logged.rir is None:
                    continue
                _merge_point(bucket, logged.exercise_id, logged.reps, logged.rir)

    skipped_rows = await db.scalars(
        select(PlannedWorkout.date).where(
            PlannedWorkout.user_id == user_id,
            PlannedWorkout.placement_id == placement.id,
            PlannedWorkout.status == STATUS_SKIPPED,
            PlannedWorkout.date >= start,
            PlannedWorkout.date <= through,
        )
    )
    skipped = [0] * (index + 1)
    for day in skipped_rows:
        week_index = (day - start).days // DAYS_IN_WEEK
        if 0 <= week_index <= index:
            skipped[week_index] += 1

    records: list[WeekRecord] = []
    for week_index in range(index + 1):
        exercises = tuple(
            ExerciseWeek(exercise_id, reps, rir)
            for exercise_id, (reps, rir) in points.get(week_index, {}).items()
        )
        records.append(WeekRecord(exercises=exercises, skipped=skipped[week_index]))
    return records


def _view(
    placement: BlockPlacement, decision: DeloadSuggestion, index: int | None
) -> SuggestionView:
    if index is None:
        message = MESSAGE_OUTSIDE
        suggest = False
        reasons: tuple[str, ...] = ()
    else:
        week_type = str(placement.weeks_snapshot[index]["week_type"])
        if week_type == "deload":
            message = MESSAGE_ALREADY
            suggest = False
            reasons = ()
        elif decision.needed:
            message = MESSAGE_SUGGEST
            suggest = True
            reasons = decision.reasons
        else:
            message = MESSAGE_QUIET
            suggest = False
            reasons = ()
    return SuggestionView(
        suggest=suggest,
        placement_id=placement.id,
        week_position=None if index is None else index + 1,
        message=message,
        reasons=tuple((code, REASON_TEXT[code]) for code in reasons),
    )


async def get_placement(
    db: AsyncSession, user_id: uuid.UUID, placement_id: uuid.UUID
) -> BlockPlacement | None:
    """Размещение только своего календаря. Чужой id выглядит как отсутствующий."""
    return await db.scalar(
        select(BlockPlacement).where(
            BlockPlacement.id == placement_id,
            BlockPlacement.user_id == user_id,
        )
    )


async def suggestion_for(
    db: AsyncSession, user_id: uuid.UUID, placement: BlockPlacement, today: dt.date
) -> SuggestionView:
    """Собирает историю и считает подсказку. Сессию не меняет."""
    index = _target_index(placement, today)
    week_type = "free" if index is None else str(placement.weeks_snapshot[index]["week_type"])
    records = await _week_records(db, user_id, placement, today)
    decision = suggest_early_deload(records, target_week_type=week_type)
    return _view(placement, decision, index)


def _deload_week(week: dict) -> dict:
    return {
        **week,
        "week_type": "deload",
        "target_rir": DEFAULT_DELOAD_RIR,
        "volume_multiplier": DEFAULT_DELOAD_VOLUME,
    }


async def accept_early_deload(
    db: AsyncSession, user_id: uuid.UUID, placement: BlockPlacement, today: dt.date
) -> AcceptResult:
    """Делает текущую неделю размещения разгрузкой, если подсказка ещё актуальна.

    Библиотечный блок не меняется. Уже выполненные и пропущенные тренировки
    остаются как были. Запланированные строки этой недели получают новые
    параметры. Открытые слоты без строки читают тот же снимок сами.
    """
    view = await suggestion_for(db, user_id, placement, today)
    if not view.suggest or view.week_position is None:
        raise DeloadError(view.message)
    index = view.week_position - 1
    weeks = [dict(week) for week in placement.weeks_snapshot]
    weeks[index] = _deload_week(weeks[index])
    placement.weeks_snapshot = weeks

    start_offset = index * DAYS_IN_WEEK
    rows = list(
        await db.scalars(
            select(PlannedWorkout).where(
                PlannedWorkout.user_id == user_id,
                PlannedWorkout.placement_id == placement.id,
                PlannedWorkout.status == STATUS_PLANNED,
                PlannedWorkout.day_offset >= start_offset,
                PlannedWorkout.day_offset < start_offset + DAYS_IN_WEEK,
            )
        )
    )
    schedule = {item["day_index"]: item for item in placement.schedule_snapshot}
    for row in rows:
        if row.day_offset is None:
            continue
        item = schedule.get(row.day_offset % DAYS_IN_WEEK)
        if item is None or item["kind"] != "workout":
            continue
        row.snapshot = apply_week(list(item["items"]), weeks[index])
    await db.flush()
    return AcceptResult(
        placement_id=placement.id,
        week_position=view.week_position,
        volume_multiplier=DEFAULT_DELOAD_VOLUME,
        target_rir=DEFAULT_DELOAD_RIR,
    )
