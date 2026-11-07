"""Сдвиг плана: чистый расчёт и применение одного и того же результата.

`compute_shift` не читает базу. Предпросмотр и применение вызывают её с одним
и тем же снимком записей, поэтому «было, станет» совпадает с тем, что запишется.

Правило границ блока периодизации (`BlockPlacement`, spec.md 4.4: «границы блоков
сдвигаются вместе с тренировками»). Для операции «сдвинуть эту и все следующие» на N дней,
где `anchor` — дата якорной тренировки, а `[start, end]` — границы блока:

- блок начинается на якоре или позже (`start >= anchor`): блок целиком едет на N дней,
  старт и конец сдвигаются. Если все его тренировки сдвинулись ровно на N, строки не
  создаются: дата тренировки блока вычисляется от старта, поэтому сдвиг меняет один старт;
- якорь внутри блока (`start < anchor <= end`): старт остаётся, конец сдвигается на N.
  Тренировки блока после якоря становятся строками плана с новой датой;
- блок целиком до якоря (`end < anchor`): границы не меняются.

Для «сдвинуть только эту» и для пропуска, перестановки границы блока не меняются:
тренировка блока становится строкой плана и выходит за рамки блока, если её перенесли.
Сдвиг, после которого конец блока оказался бы раньше его старта, отклоняется.

Занятые блоками дни (`blocked_dates`) — отдельный механизм: цепочка перешагивает такой день.
Границы блоков периодизации не сводятся к нему: они двигаются по правилу выше.
"""

import datetime as dt
import uuid
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.block import BlockPlacement
from app.models.plan import (
    KIND_REST,
    KIND_WORKOUT,
    STATUS_PLANNED,
    STATUS_SKIPPED,
    PlanChangeLog,
    PlannedWorkout,
)
from app.services.block_calendar import (
    PlacementSpan,
    find_open_slot,
    load_placements,
    open_slots,
    slot_row,
)
from app.services.block_rules import Slot
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
    placement_id: uuid.UUID | None = None
    day_offset: int | None = None
    # Тренировка блока без строки в базе: её дата вычисляется от старта блока.
    virtual: bool = False


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
    virtual: bool = False
    placement_id: uuid.UUID | None = None


@dataclass(frozen=True, slots=True)
class BlockChange:
    """Новые границы блока после сдвига. `absorbed`: его тренировки едут вместе со стартом."""

    placement_id: uuid.UUID
    name: str
    start_before: dt.date
    start_after: dt.date
    end_before: dt.date | None
    end_after: dt.date | None
    absorbed: bool


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
    blocks: tuple[BlockChange, ...] = field(default=())

    @property
    def resolutions(self) -> tuple[str, ...]:
        if not self.conflicts:
            return ()
        # «Оставить две» имеет смысл только когда день занят другой тренировкой.
        # Отдых, две записи отдыха или граница блока так не совмещаются.
        if all(conflict.reason == REASON_OCCUPIED for conflict in self.conflicts):
            return (RESOLUTION_CASCADE, RESOLUTION_STACK, RESOLUTION_CANCEL)
        return (RESOLUTION_CASCADE, RESOLUTION_CANCEL)

    @property
    def is_empty(self) -> bool:
        return not self.changes and not self.blocks


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
                virtual=entry.virtual,
                placement_id=entry.placement_id,
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


def _block_changes(
    entries: Sequence[ShiftEntry],
    placements: Sequence[PlacementSpan],
    anchor_date: dt.date,
    days: int,
    changes: Sequence[ShiftChange],
) -> tuple[BlockChange, ...]:
    """Границы блоков по правилу из docstring модуля. Здесь же отказ, если блок опустеет."""
    delta = dt.timedelta(days=days)
    change_by_id = {change.id: change for change in changes}
    result: list[BlockChange] = []
    for span in placements:
        if span.end is None:
            if span.start < anchor_date:
                raise ShiftError(
                    f"Блок «{span.name}» без конца можно сдвинуть только целиком, "
                    "от его первого дня. Одну тренировку перенесите отдельно."
                )
            start_after, end_after = span.start + delta, None
            absorbed = all(
                _follows_start(slot, change_by_id.get(slot.id), days)
                for slot in entries
                if slot.virtual and slot.placement_id == span.id
            )
        elif span.start >= anchor_date:
            start_after, end_after = span.start + delta, span.end + delta
            absorbed = all(
                _follows_start(slot, change_by_id.get(slot.id), days)
                for slot in entries
                if slot.virtual and slot.placement_id == span.id
            )
        elif span.end >= anchor_date:
            start_after, end_after = span.start, span.end + delta
            absorbed = False
        else:
            continue
        if end_after is not None and end_after < start_after:
            raise ShiftError(
                f"Сдвиг сделал бы блок «{span.name}» пустым: он кончился бы раньше старта"
            )
        if (start_after, end_after) != (span.start, span.end):
            result.append(
                BlockChange(
                    placement_id=span.id,
                    name=span.name,
                    start_before=span.start,
                    start_after=start_after,
                    end_before=span.end,
                    end_after=end_after,
                    absorbed=absorbed,
                )
            )
    return tuple(result)


def _follows_start(slot: ShiftEntry, change: ShiftChange | None, days: int) -> bool:
    """Тренировка блока сдвинулась ровно на N дней и не меняла статус: строка не нужна."""
    if change is None:
        return False
    moved = change.date_after - slot.date == dt.timedelta(days=days)
    return moved and change.status_after == change.status_before


def _is_swappable(entry: ShiftEntry) -> bool:
    return entry.kind == KIND_WORKOUT and entry.status == STATUS_PLANNED and not entry.is_fixed


def compute_shift(
    entries: Sequence[ShiftEntry],
    *,
    operation: str,
    anchor_id: uuid.UUID,
    days: int | None = None,
    other_id: uuid.UUID | None = None,
    resolution: str | None = None,
    blocked_dates: Iterable[dt.date] = (),
    placements: Iterable[PlacementSpan] = (),
) -> ShiftPlan:
    """Считает, какие записи куда переедут, границы блоков и конфликты занятых дней.

    `resolution=None` — прямой сдвиг на N дней: конфликты остаются в ответе.
    `cascade` перешагивает занятые дни, `stack` оставляет две тренировки в одном
    дне, `cancel` ничего не меняет. `blocked_dates` — дни, которые нельзя занять.
    `placements` — размещения блоков с их границами (правило в docstring модуля).
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
    plan = _shift_plan(entries, moving, shift_days, resolution, blocked)
    if operation != OP_SHIFT_FOLLOWING or resolution == RESOLUTION_CANCEL:
        return plan
    blocks = _block_changes(entries, tuple(placements), anchor.date, shift_days, plan.changes)
    return ShiftPlan(plan.changes, plan.conflicts, blocks)


def _entry_from_row(row: PlannedWorkout) -> ShiftEntry:
    return ShiftEntry(
        id=row.id,
        date=row.date,
        kind=row.kind,
        status=row.status,
        is_fixed=row.is_fixed,
        position=row.position,
        name=row.name,
        placement_id=row.placement_id,
        day_offset=row.day_offset,
    )


def _entry_from_slot(slot: Slot) -> ShiftEntry:
    is_workout = slot.kind == KIND_WORKOUT
    return ShiftEntry(
        id=slot.id,
        date=slot.date,
        kind=slot.kind,
        status=STATUS_PLANNED if is_workout else None,
        is_fixed=False,
        position=0,
        name=slot.name,
        placement_id=slot.placement_id,
        day_offset=slot.day_offset,
        virtual=True,
    )


@dataclass(slots=True)
class _PlanState:
    rows: list[PlannedWorkout]
    placements: dict[uuid.UUID, BlockPlacement]
    slots: list[Slot]

    @property
    def entries(self) -> list[ShiftEntry]:
        return [_entry_from_row(row) for row in self.rows] + [
            _entry_from_slot(slot) for slot in self.slots
        ]

    @property
    def spans(self) -> list[PlacementSpan]:
        return [
            PlacementSpan(id=p.id, name=p.name, start=p.start_date, end=p.end_date)
            for p in self.placements.values()
        ]


async def _load_state(
    db: AsyncSession, user_id: uuid.UUID, focus_id: uuid.UUID | None = None
) -> _PlanState:
    result = await db.scalars(select(PlannedWorkout).where(PlannedWorkout.user_id == user_id))
    rows = list(result.all())
    placements = {p.id: p for p in await load_placements(db, user_id)}
    slots = await open_slots(db, user_id)
    known = {row.id for row in rows} | {slot.id for slot in slots}
    if focus_id is not None and focus_id not in known:
        focused = await find_open_slot(db, user_id, focus_id)
        if focused is not None:
            slots.append(focused)
    return _PlanState(rows=rows, placements=placements, slots=slots)


def _payload(
    operation: str,
    days: int | None,
    resolution: str | None,
    items: Sequence[dict[str, Any]],
    blocks: Sequence[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "operation": operation,
        "days": days,
        "resolution": resolution,
        "changes": list(items),
        "blocks": list(blocks),
    }


def _change_item(
    entry_id: uuid.UUID,
    date: dt.date,
    status: str | None,
    position: int,
    *,
    virtual: bool,
    materialized: bool,
) -> dict[str, Any]:
    return {
        "id": str(entry_id),
        "date": date.isoformat(),
        "status": status,
        "position": position,
        "virtual": virtual,
        "materialized": materialized,
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


def _ensure_days_compatible(entries: Sequence[ShiftEntry]) -> None:
    by_day: dict[dt.date, list[ShiftEntry]] = defaultdict(list)
    for entry in entries:
        by_day[entry.date].append(entry)
    for day, group in by_day.items():
        kinds = {entry.kind for entry in group}
        rest_count = sum(1 for entry in group if entry.kind == KIND_REST)
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
    state = await _load_state(db, user_id, anchor_id)
    return compute_shift(
        state.entries,
        operation=operation,
        anchor_id=anchor_id,
        days=days,
        other_id=other_id,
        resolution=resolution,
        placements=state.spans,
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
    """Записывает результат `compute_shift` и кладёт прежнее состояние в журнал.

    Строки создаются только для тренировок блока, которые действительно изменились.
    Сдвиг блока целиком меняет его старт и строк не создаёт.
    """
    if resolution == RESOLUTION_CANCEL:
        return ShiftPlan((), ()), None

    await _lock_user_plan(db, user_id)
    state = await _load_state(db, user_id, anchor_id)
    plan = compute_shift(
        state.entries,
        operation=operation,
        anchor_id=anchor_id,
        days=days,
        other_id=other_id,
        resolution=resolution,
        placements=state.spans,
    )
    if plan.conflicts:
        raise ShiftConflictError(
            "Сдвиг затрагивает занятый день. Выберите вариант в предпросмотре или отмените."
        )
    if plan.is_empty:
        return plan, None

    rows_by_id = {row.id: row for row in state.rows}
    slots_by_id = {slot.id: slot for slot in state.slots}
    absorbed = {block.placement_id for block in plan.blocks if block.absorbed}
    items: list[dict[str, Any]] = []

    for change in plan.changes:
        if change.virtual:
            continue
        row = rows_by_id[change.id]
        items.append(
            _change_item(
                change.id,
                change.date_before,
                change.status_before,
                change.position_before,
                virtual=False,
                materialized=False,
            )
        )
        row.date = change.date_after
        row.status = change.status_after
        row.position = change.position_after

    # Тренировки блока, которые становятся строками: изменённые и, при сдвиге старта,
    # все остальные тренировки этого блока (иначе старт сдвинул бы их вслед за собой).
    to_materialize: dict[uuid.UUID, ShiftChange | None] = {}
    for change in plan.changes:
        if change.virtual and change.placement_id not in absorbed:
            to_materialize[change.id] = change
    for block in plan.blocks:
        if block.start_after != block.start_before and not block.absorbed:
            for slot in state.slots:
                if slot.placement_id == block.placement_id:
                    to_materialize.setdefault(slot.id, None)

    for slot_key, change in to_materialize.items():
        slot = slots_by_id[slot_key]
        row = slot_row(user_id, slot)
        before = _entry_from_slot(slot)
        if change is not None:
            row.date = change.date_after
            row.status = change.status_after
            row.position = change.position_after
        db.add(row)
        items.append(
            _change_item(
                slot.id,
                before.date,
                before.status,
                before.position,
                virtual=True,
                materialized=True,
            )
        )

    for change in plan.changes:
        if change.virtual and change.placement_id in absorbed:
            items.append(
                _change_item(
                    change.id,
                    change.date_before,
                    change.status_before,
                    change.position_before,
                    virtual=True,
                    materialized=False,
                )
            )

    block_items: list[dict[str, Any]] = []
    for block in plan.blocks:
        placement = state.placements[block.placement_id]
        block_items.append(
            {
                "placement_id": str(block.placement_id),
                "start": placement.start_date.isoformat(),
                "end": None if placement.end_date is None else placement.end_date.isoformat(),
            }
        )
        placement.start_date = block.start_after
        placement.end_date = block.end_after

    log = PlanChangeLog(
        user_id=user_id,
        operation=operation,
        payload=_payload(operation, days, resolution, items, block_items),
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
    """Возвращает даты, статусы и границы последней операции и убирает её из журнала.

    Строки, созданные операцией для тренировок блока, удаляются: тренировка снова
    становится открытой и следует за стартом блока.
    """
    await _lock_user_plan(db, user_id)
    log = await db.scalar(
        select(PlanChangeLog)
        .where(PlanChangeLog.user_id == user_id)
        .order_by(PlanChangeLog.seq.desc())
        .limit(1)
    )
    if log is None:
        raise ShiftError("Нет операции для отмены", missing=True)

    state = await _load_state(db, user_id)
    rows_by_id = {row.id: row for row in state.rows}
    restored: list[ShiftChange] = []
    # Savepoint: если итог занят, откатываем уже сделанные правки, а не оставляем их в сессии.
    async with db.begin_nested():
        for item in log.payload["changes"]:
            entry_id = uuid.UUID(item["id"])
            if item.get("virtual"):
                row = rows_by_id.get(entry_id)
                if item.get("materialized") and row is not None:
                    await db.delete(row)
                continue
            row = rows_by_id.get(entry_id)
            if row is None:
                raise ShiftError("Запись из истории уже удалена, отмена невозможна")
            restored.append(
                ShiftChange(
                    id=row.id,
                    name=row.name,
                    kind=row.kind,
                    date_before=row.date,
                    date_after=dt.date.fromisoformat(item["date"]),
                    status_before=row.status,
                    status_after=item["status"],
                    position_before=row.position,
                    position_after=int(item["position"]),
                )
            )
            row.date = dt.date.fromisoformat(item["date"])
            row.status = item["status"]
            row.position = int(item["position"])

        for block_item in log.payload.get("blocks", []):
            placement = state.placements.get(uuid.UUID(block_item["placement_id"]))
            if placement is None:
                raise ShiftError("Блок из истории уже удалён, отмена невозможна")
            placement.start_date = dt.date.fromisoformat(block_item["start"])
            saved_end = block_item["end"]
            placement.end_date = dt.date.fromisoformat(saved_end) if saved_end else None

        await db.flush()
        remaining = await _load_state(db, user_id)
        _ensure_days_compatible(remaining.entries)

    log_id = log.id
    await db.delete(log)
    await db.flush()
    changes = tuple(
        sorted(restored, key=lambda change: (change.date_after, change.position_after, change.id))
    )
    return ShiftPlan(changes, ()), log_id
