"""Тренировки блоков в календаре: слоты без строк и их превращение в строки плана.

Слот, которого нет в таблице `planned_workouts`, считается «открытым»: он виден в календаре,
но в базе не хранится. Как только тренировку отметили, перенесли или сдвинули, для неё
создаётся строка с тем же id (`slot_row`). Строка скрывает слот по паре
(`placement_id`, `day_offset`).
"""

import datetime as dt
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.block import BlockPlacement
from app.models.plan import KIND_WORKOUT, STATUS_PLANNED, PlannedWorkout
from app.services.block_rules import REPEAT_LOOKUP_DAYS, Slot, build_slots


@dataclass(frozen=True, slots=True)
class PlacementSpan:
    """Границы размещения блока на календаре: то, что двигает сдвиг.

    `end is None` — блок без конца, циклы повторяются.
    """

    id: uuid.UUID
    name: str
    start: dt.date
    end: dt.date | None


async def load_placements(db: AsyncSession, user_id: uuid.UUID) -> list[BlockPlacement]:
    result = await db.scalars(
        select(BlockPlacement)
        .where(BlockPlacement.user_id == user_id)
        .order_by(BlockPlacement.start_date, BlockPlacement.id)
    )
    return list(result.all())


def placement_slots(
    placement: BlockPlacement, window: tuple[dt.date, dt.date] | None = None
) -> list[Slot]:
    return build_slots(
        placement.id,
        placement.start_date,
        placement.length_weeks,
        list(placement.weeks_snapshot),
        list(placement.schedule_snapshot),
        placement.cycle_days,
        repeats=placement.repeats,
        window=window,
    )


async def _materialized_keys(db: AsyncSession, user_id: uuid.UUID) -> set[tuple[uuid.UUID, int]]:
    result = await db.execute(
        select(PlannedWorkout.placement_id, PlannedWorkout.day_offset).where(
            PlannedWorkout.user_id == user_id,
            PlannedWorkout.placement_id.is_not(None),
        )
    )
    return {(placement_id, offset) for placement_id, offset in result.all() if offset is not None}


async def open_slots(
    db: AsyncSession,
    user_id: uuid.UUID,
    start: dt.date | None = None,
    end: dt.date | None = None,
) -> list[Slot]:
    """Слоты блоков, для которых строки ещё нет. Диапазон дат необязателен."""
    placements = await load_placements(db, user_id)
    if not placements:
        return []
    taken = await _materialized_keys(db, user_id)
    slots: list[Slot] = []
    window = (start, end) if start is not None and end is not None else None
    for placement in placements:
        # Без окна бесконечный блок не разворачиваем: иначе слотов нет конца.
        if placement.repeats and window is None:
            continue
        for slot in placement_slots(placement, window):
            if (placement.id, slot.day_offset) in taken:
                continue
            if start is not None and slot.date < start:
                continue
            if end is not None and slot.date > end:
                continue
            slots.append(slot)
    return slots


async def find_open_slot(db: AsyncSession, user_id: uuid.UUID, entry_id: uuid.UUID) -> Slot | None:
    placements = await load_placements(db, user_id)
    if not placements:
        return None
    taken = await _materialized_keys(db, user_id)
    for placement in placements:
        if placement.repeats:
            slot = _repeating_slot(placement, entry_id, taken)
        else:
            slot = next(
                (
                    item
                    for item in placement_slots(placement)
                    if item.id == entry_id and (placement.id, item.day_offset) not in taken
                ),
                None,
            )
        if slot is not None:
            return slot
    return None


def _repeating_slot(
    placement: BlockPlacement, entry_id: uuid.UUID, taken: set[tuple[uuid.UUID, int]]
) -> Slot | None:
    horizon = placement.start_date + dt.timedelta(days=REPEAT_LOOKUP_DAYS)
    for offset in range(REPEAT_LOOKUP_DAYS):
        if (placement.id, offset) in taken:
            continue
        day = placement.start_date + dt.timedelta(days=offset)
        for slot in placement_slots(placement, (day, day)):
            if slot.id == entry_id:
                return slot
        if day >= horizon:
            break
    return None


def slot_row(user_id: uuid.UUID, slot: Slot) -> PlannedWorkout:
    """Строка плана для слота. Сама в сессию не добавляется: это решает вызывающий код."""
    is_workout = slot.kind == KIND_WORKOUT
    return PlannedWorkout(
        id=slot.id,
        user_id=user_id,
        date=slot.date,
        kind=slot.kind,
        template_id=None,
        name=slot.name,
        snapshot=list(slot.items) if is_workout else [],
        status=STATUS_PLANNED if is_workout else None,
        is_fixed=False,
        position=0,
        placement_id=slot.placement_id,
        day_offset=slot.day_offset,
    )
