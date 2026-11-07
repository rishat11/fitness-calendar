"""Сдвиг плана: чистый расчёт и применение одного и того же результата.

`compute_shift` не читает базу. Предпросмотр и применение вызывают её с одним
и тем же снимком записей, поэтому «было, станет» совпадает с тем, что запишется.
Границы блоков периодизации придут на этапе 3 через `blocked_dates`: такой день
нельзя занять, цепочка его перешагивает.
"""

import datetime as dt
import uuid
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.plan import (
    KIND_REST,
    KIND_WORKOUT,
    STATUS_PLANNED,
    STATUS_SKIPPED,
    PlanChangeLog,
    PlannedWorkout,
)
from app.services.plan import _lock_user_plan

HISTORY_LIMIT = 20
MAX_SHIFT_DAYS = 366

OP_SHIFT_FOLLOWING = "shift_following"
OP_SHIFT_ONLY = "shift_only"
OP_SKIP = "skip"
OP_SWAP = "swap"

RESOLUTION_CASCADE = "cascade"
RESOLUTION_STACK = "stack"
RESOLUTION_CANCEL = "cancel"

REASON_OCCUPIED = "occupied"
REASON_BLOCKED = "blocked"

ConflictReason = Literal["occupied", "blocked"]


class ShiftError(Exception):
    """Операцию нельзя даже посчитать: записи нет или она не двигается."""

    def __init__(self, message: str, *, missing: bool = False) -> None:
        super().__init__(message)
        self.missing = missing


class ShiftConflictError(Exception):
    """Сдвиг посчитан, но без выбранного варианта его нельзя записать."""


@dataclass(frozen=True, slots=True)
class ShiftEntry:
    id: uuid.UUID
    date: dt.date
    kind: str
    status: str | None
    is_fixed: bool
    position: int
    name: str | None


@dataclass(frozen=True, slots=True)
class ShiftChange:
    id: uuid.UUID
    name: str | None
    kind: str
    date_before: dt.date
    date_after: dt.date
    status_before: str | None
    status_after: str | None
    position_before: int
    position_after: int


@dataclass(frozen=True, slots=True)
class ShiftConflict:
    entry_id: uuid.UUID
    date: dt.date
    reason: ConflictReason
    message: str


@dataclass(frozen=True, slots=True)
class ShiftPlan:
    changes: tuple[ShiftChange, ...]
    conflicts: tuple[ShiftConflict, ...]

    @property
    def resolutions(self) -> tuple[str, ...]:
        if not self.conflicts:
            return ()
        # «Оставить две» имеет смысл только когда день занят другой тренировкой.
        # Отдых, две записи отдыха или граница блока так не совмещаются.
        if all(conflict.reason == REASON_OCCUPIED for conflict in self.conflicts):
            return (RESOLUTION_CASCADE, RESOLUTION_STACK, RESOLUTION_CANCEL)
        return (RESOLUTION_CASCADE, RESOLUTION_CANCEL)


def _is_movable(entry: ShiftEntry) -> bool:
    """Запланированная тренировка или незафиксированный день отдыха."""
    if entry.is_fixed:
        return False
    if entry.kind == KIND_REST:
        return True
    return entry.status == STATUS_PLANNED


def _require(entry: ShiftEntry | None) -> ShiftEntry:
    if entry is None:
        raise ShiftError("Запись плана не найдена", missing=True)
    return entry


def _changes_for(
    entries: Sequence[ShiftEntry],
    placement: dict[uuid.UUID, dt.date],
    statuses: dict[uuid.UUID, str | None] | None = None,
) -> tuple[ShiftChange, ...]:
    changes: list[ShiftChange] = []
    for entry in entries:
        new_date = placement.get(entry.id, entry.date)
        new_status = entry.status if statuses is None else statuses.get(entry.id, entry.status)
        if new_date == entry.date and new_status == entry.status:
            continue
        changes.append(
            ShiftChange(
                id=entry.id,
                name=entry.name,
                kind=entry.kind,
                date_before=entry.date,
                date_after=new_date,
                status_before=entry.status,
                status_after=new_status,
                position_before=entry.position,
                position_after=entry.position,
            )
        )
    changes.sort(key=lambda change: (change.date_before, change.position_before, change.id))
    return tuple(changes)


def _conflict_message(reason: ConflictReason) -> str:
    if reason == REASON_OCCUPIED:
        return "Тренировка попадает на занятый день"
    return "Этот день нельзя совместить с переносимой записью"


def _conflicts_for(
    entries: Sequence[ShiftEntry],
    moving_ids: set[uuid.UUID],
    placement: dict[uuid.UUID, dt.date],
    blocked_dates: frozenset[dt.date],
) -> tuple[ShiftConflict, ...]:
    final_date = {entry.id: placement.get(entry.id, entry.date) for entry in entries}
    by_day: dict[dt.date, list[ShiftEntry]] = defaultdict(list)
    for entry in entries:
        by_day[final_date[entry.id]].append(entry)

    conflicts: list[ShiftConflict] = []
    for day, group in by_day.items():
        arrivals = [
            entry
            for entry in group
            if entry.id in moving_ids and final_date[entry.id] != entry.date
        ]
        if not arrivals:
            continue
        stays = [entry for entry in group if entry not in arrivals]
        has_rest = any(entry.kind == KIND_REST for entry in group)
        has_workout = any(entry.kind == KIND_WORKOUT for entry in group)
        rest_count = sum(1 for entry in group if entry.kind == KIND_REST)
        staying_workouts = [entry for entry in stays if entry.kind == KIND_WORKOUT]
        arriving_workouts = [entry for entry in arrivals if entry.kind == KIND_WORKOUT]
        if day in blocked_dates or (has_rest and has_workout) or rest_count > 1:
            reason: ConflictReason = REASON_BLOCKED
        elif staying_workouts and arriving_workouts:
            reason = REASON_OCCUPIED
        else:
            continue
        message = _conflict_message(reason)
        conflicts.extend(
            ShiftConflict(entry_id=entry.id, date=day, reason=reason, message=message)
            for entry in arrivals
        )
    conflicts.sort(key=lambda conflict: (conflict.date, conflict.entry_id))
    return tuple(conflicts)


def _moving_chain(
    entries: Sequence[ShiftEntry], anchor: ShiftEntry, *, only_anchor: bool
) -> list[ShiftEntry]:
    if not _is_movable(anchor):
        raise ShiftError(
            "Эта запись не двигается: она выполнена, пропущена, перенесена или зафиксирована"
        )
    if only_anchor:
        return [anchor]
    return [entry for entry in entries if entry.date >= anchor.date and _is_movable(entry)]


def _naive_placement(moving: Sequence[ShiftEntry], days: int) -> dict[uuid.UUID, dt.date]:
    delta = dt.timedelta(days=days)
    return {entry.id: entry.date + delta for entry in moving}


def _cascade_placement(
    entries: Sequence[ShiftEntry],
    moving: Sequence[ShiftEntry],
    days: int,
    blocked_dates: frozenset[dt.date],
) -> dict[uuid.UUID, dt.date]:
    """Сдвигает слоты по дням и перешагивает занятые, сохраняя порядок слотов.

    Записи одного дня едут вместе. Сначала ставится задний край цепочки, чтобы
    передний, упёршись в препятствие, уехал дальше и не поменялся с ним местами.
    """
    moving_ids = {entry.id for entry in moving}
    stayer_days = {entry.date for entry in entries if entry.id not in moving_ids}
    slots: dict[dt.date, list[ShiftEntry]] = defaultdict(list)
    for entry in moving:
        slots[entry.date].append(entry)

    direction = 1 if days > 0 else -1
    taken: set[dt.date] = set()
    placement: dict[uuid.UUID, dt.date] = {}
    for original in sorted(slots, reverse=days < 0):
        target = original + dt.timedelta(days=days)
        hops = 0
        while target in stayer_days or target in taken or target in blocked_dates:
            target += dt.timedelta(days=direction)
            hops += 1
            if hops > MAX_SHIFT_DAYS:
                raise ShiftError("Не удалось найти свободный день для сдвига")
        taken.add(target)
        for entry in slots[original]:
            placement[entry.id] = target
    return placement


def _require_days(days: int | None) -> int:
    if days is None or days == 0 or abs(days) > MAX_SHIFT_DAYS:
        raise ShiftError("Укажите число дней от -366 до 366, кроме нуля")
    return days


def _shift_plan(
    entries: Sequence[ShiftEntry],
    moving: Sequence[ShiftEntry],
    days: int,
    resolution: str | None,
    blocked_dates: frozenset[dt.date],
) -> ShiftPlan:
    moving_ids = {entry.id for entry in moving}
    if resolution == RESOLUTION_CASCADE:
        placement = _cascade_placement(entries, moving, days, blocked_dates)
    else:
        placement = _naive_placement(moving, days)
    changes = _changes_for(entries, placement)
    conflicts = _conflicts_for(entries, moving_ids, placement, blocked_dates)
    if resolution == RESOLUTION_STACK:
        conflicts = tuple(conflict for conflict in conflicts if conflict.reason != REASON_OCCUPIED)
    if resolution == RESOLUTION_CANCEL:
        return ShiftPlan((), conflicts)
    return ShiftPlan(changes, conflicts)


def compute_shift(
    entries: Sequence[ShiftEntry],
    *,
    operation: str,
    anchor_id: uuid.UUID,
    days: int | None = None,
    other_id: uuid.UUID | None = None,
    resolution: str | None = None,
    blocked_dates: Iterable[dt.date] = (),
) -> ShiftPlan:
    """Считает, какие записи куда переедут, и конфликты занятых дней.

    `resolution=None` — прямой сдвиг на N дней: конфликты остаются в ответе.
    `cascade` перешагивает занятые дни, `stack` оставляет две тренировки в одном
    дне, `cancel` ничего не меняет. `blocked_dates` — дни, которые нельзя занять
    (границы блоков, этап 3).
    """
    blocked = frozenset(blocked_dates)
    by_id = {entry.id: entry for entry in entries}
    anchor = _require(by_id.get(anchor_id))

    if operation == OP_SKIP:
        if anchor.kind != KIND_WORKOUT or anchor.status != STATUS_PLANNED:
            raise ShiftError("Пропустить можно только запланированную тренировку")
        change = _changes_for(entries, {}, {anchor.id: STATUS_SKIPPED})
        return ShiftPlan(change, ())

    if operation == OP_SWAP:
        other = _require(by_id.get(other_id) if other_id is not None else None)
        if other.id == anchor.id:
            raise ShiftError("Нельзя поменять тренировку саму с собой")
        if not _is_swappable(anchor) or not _is_swappable(other):
            raise ShiftError("Поменять местами можно только две запланированные тренировки")
        if anchor.date == other.date:
            raise ShiftError("Эти тренировки уже стоят в один день")
        placement = {anchor.id: other.date, other.id: anchor.date}
        return ShiftPlan(_changes_for(entries, placement), ())

    if operation not in (OP_SHIFT_FOLLOWING, OP_SHIFT_ONLY):
        raise ShiftError("Неизвестная операция сдвига")

    shift_days = _require_days(days)
    moving = _moving_chain(entries, anchor, only_anchor=operation == OP_SHIFT_ONLY)
    return _shift_plan(entries, moving, shift_days, resolution, blocked)


def _is_swappable(entry: ShiftEntry) -> bool:
    return entry.kind == KIND_WORKOUT and entry.status == STATUS_PLANNED and not entry.is_fixed


def _entry_from_row(row: PlannedWorkout) -> ShiftEntry:
    return ShiftEntry(
        id=row.id,
        date=row.date,
        kind=row.kind,
        status=row.status,
        is_fixed=row.is_fixed,
        position=row.position,
        name=row.name,
    )


async def _load_rows(db: AsyncSession, user_id: uuid.UUID) -> list[PlannedWorkout]:
    result = await db.scalars(select(PlannedWorkout).where(PlannedWorkout.user_id == user_id))
    return list(result.all())


def _payload(
    operation: str, days: int | None, resolution: str | None, changes: Sequence[ShiftChange]
) -> dict[str, Any]:
    return {
        "operation": operation,
        "days": days,
        "resolution": resolution,
        "changes": [
            {
                "id": str(change.id),
                "date": change.date_before.isoformat(),
                "status": change.status_before,
                "position": change.position_before,
            }
            for change in changes
        ],
    }


async def _trim_history(db: AsyncSession, user_id: uuid.UUID) -> None:
    stale_ids = list(
        await db.scalars(
            select(PlanChangeLog.id)
            .where(PlanChangeLog.user_id == user_id)
            .order_by(PlanChangeLog.seq.desc())
            .offset(HISTORY_LIMIT)
        )
    )
    if stale_ids:
        await db.execute(delete(PlanChangeLog).where(PlanChangeLog.id.in_(stale_ids)))


def _ensure_days_compatible(
    rows: Sequence[PlannedWorkout], dates: dict[uuid.UUID, dt.date]
) -> None:
    by_day: dict[dt.date, list[PlannedWorkout]] = defaultdict(list)
    for row in rows:
        by_day[dates[row.id]].append(row)
    for day, group in by_day.items():
        kinds = {row.kind for row in group}
        rest_count = sum(1 for row in group if row.kind == KIND_REST)
        if KIND_REST in kinds and KIND_WORKOUT in kinds:
            raise ShiftConflictError(
                f"Отмена невозможна: {day.isoformat()} совмещает отдых и тренировку"
            )
        if rest_count > 1:
            raise ShiftConflictError(
                f"Отмена невозможна: на {day.isoformat()} несколько дней отдыха"
            )


async def preview_shift(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    operation: str,
    anchor_id: uuid.UUID,
    days: int | None = None,
    other_id: uuid.UUID | None = None,
    resolution: str | None = None,
) -> ShiftPlan:
    rows = await _load_rows(db, user_id)
    return compute_shift(
        [_entry_from_row(row) for row in rows],
        operation=operation,
        anchor_id=anchor_id,
        days=days,
        other_id=other_id,
        resolution=resolution,
    )


async def apply_shift(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    operation: str,
    anchor_id: uuid.UUID,
    days: int | None = None,
    other_id: uuid.UUID | None = None,
    resolution: str | None = None,
) -> tuple[ShiftPlan, uuid.UUID | None]:
    """Записывает результат `compute_shift` и кладёт прежние даты в журнал."""
    if resolution == RESOLUTION_CANCEL:
        return ShiftPlan((), ()), None

    await _lock_user_plan(db, user_id)
    rows = await _load_rows(db, user_id)
    plan = compute_shift(
        [_entry_from_row(row) for row in rows],
        operation=operation,
        anchor_id=anchor_id,
        days=days,
        other_id=other_id,
        resolution=resolution,
    )
    if plan.conflicts:
        raise ShiftConflictError(
            "Сдвиг затрагивает занятый день. Выберите вариант в предпросмотре или отмените."
        )
    if not plan.changes:
        return plan, None

    by_id = {row.id: row for row in rows}
    for change in plan.changes:
        row = by_id[change.id]
        row.date = change.date_after
        row.status = change.status_after
        row.position = change.position_after

    log = PlanChangeLog(
        user_id=user_id,
        operation=operation,
        payload=_payload(operation, days, resolution, plan.changes),
    )
    db.add(log)
    await db.flush()
    await _trim_history(db, user_id)
    await db.flush()
    return plan, log.id


async def list_shift_history(db: AsyncSession, user_id: uuid.UUID) -> Sequence[PlanChangeLog]:
    result = await db.scalars(
        select(PlanChangeLog)
        .where(PlanChangeLog.user_id == user_id)
        .order_by(PlanChangeLog.seq.desc())
        .limit(HISTORY_LIMIT)
    )
    return result.all()


async def undo_last_shift(db: AsyncSession, user_id: uuid.UUID) -> tuple[ShiftPlan, uuid.UUID]:
    """Возвращает даты и статусы последней операции и убирает её из журнала."""
    await _lock_user_plan(db, user_id)
    log = await db.scalar(
        select(PlanChangeLog)
        .where(PlanChangeLog.user_id == user_id)
        .order_by(PlanChangeLog.seq.desc())
        .limit(1)
    )
    if log is None:
        raise ShiftError("Нет операции для отмены", missing=True)

    rows = await _load_rows(db, user_id)
    by_id = {row.id: row for row in rows}
    restored: list[tuple[PlannedWorkout, ShiftChange]] = []
    dates = {row.id: row.date for row in rows}
    for item in log.payload["changes"]:
        entry_id = uuid.UUID(item["id"])
        row = by_id.get(entry_id)
        if row is None:
            raise ShiftError("Запись из истории уже удалена, отмена невозможна")
        previous_date = dt.date.fromisoformat(item["date"])
        previous_status = item["status"]
        previous_position = int(item["position"])
        dates[row.id] = previous_date
        restored.append(
            (
                row,
                ShiftChange(
                    id=row.id,
                    name=row.name,
                    kind=row.kind,
                    date_before=row.date,
                    date_after=previous_date,
                    status_before=row.status,
                    status_after=previous_status,
                    position_before=row.position,
                    position_after=previous_position,
                ),
            )
        )

    # Проверяем итог до записи: иначе отказ оставит в сессии уже сдвинутые даты.
    _ensure_days_compatible(rows, dates)
    for row, change in restored:
        row.date = change.date_after
        row.status = change.status_after
        row.position = change.position_after

    log_id = log.id
    await db.delete(log)
    await db.flush()
    changes = tuple(
        sorted(
            (change for _, change in restored),
            key=lambda change: (change.date_after, change.position_after, change.id),
        )
    )
    return ShiftPlan(changes, ()), log_id
