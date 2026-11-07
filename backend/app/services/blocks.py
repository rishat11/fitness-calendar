"""Блоки периодизации: библиотека блоков и их применение к календарю с датой старта.

Применение не создаёт строку на каждый день: `BlockPlacement` хранит старт и снимок
недель и расписания, а тренировки вычисляются в `block_calendar`. Так сдвиг блока меняет
одну дату, а не сотни строк.
"""

import datetime as dt
import uuid
from collections.abc import Sequence

from sqlalchemy import delete, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.block import Block, BlockPlacement, BlockScheduleItem, BlockWeek
from app.models.plan import STATUS_PLANNED, PlannedWorkout
from app.schemas.block import BlockInput, BlockScheduleInput, BlockWeekInput
from app.services.block_calendar import load_placements
from app.services.block_rules import REPEAT_CONFLICT_DAYS, block_end, build_slots
from app.services.deload import DeloadRoomError, WeekSpec, with_default_deload
from app.services.plan import _lock_user_plan, list_entries, snapshot_from_template
from app.services.workouts import COPY_SUFFIX, NAME_MAX, get_template


class BlockError(Exception):
    """Блок нельзя сохранить или применить: например, тренировка не из библиотеки."""


class BlockConflictError(Exception):
    """Блок нельзя применить: даты блока уже заняты планом."""


async def list_blocks(db: AsyncSession, user_id: uuid.UUID) -> Sequence[Block]:
    result = await db.scalars(
        select(Block).where(Block.user_id == user_id).order_by(Block.created_at, Block.id)
    )
    return result.all()


async def get_block(db: AsyncSession, user_id: uuid.UUID, block_id: uuid.UUID) -> Block | None:
    """Возвращает блок только если он принадлежит пользователю."""
    return await db.scalar(select(Block).where(Block.id == block_id, Block.user_id == user_id))


def _specs(weeks: Sequence[BlockWeekInput]) -> list[WeekSpec]:
    return [
        WeekSpec(
            week_type=week.week_type,
            rep_min=week.rep_min,
            rep_max=week.rep_max,
            target_rir=week.target_rir,
            volume_multiplier=week.volume_multiplier,
        )
        for week in weeks
    ]


def _build_weeks(inputs: Sequence[WeekSpec]) -> list[BlockWeek]:
    return [
        BlockWeek(
            position=position,
            week_type=week.week_type,
            rep_min=week.rep_min,
            rep_max=week.rep_max,
            target_rir=week.target_rir,
            volume_multiplier=week.volume_multiplier,
        )
        for position, week in enumerate(inputs, start=1)
    ]


async def _build_schedule(
    db: AsyncSession, user_id: uuid.UUID, inputs: Sequence[BlockScheduleInput]
) -> list[BlockScheduleItem]:
    """Снимок тренировок расписания: правка библиотеки после сохранения блок не меняет."""
    items: list[BlockScheduleItem] = []
    for entry in inputs:
        if entry.kind == "rest":
            items.append(
                BlockScheduleItem(day_index=entry.day_index, kind="rest", name=None, snapshot=[])
            )
            continue
        template = await get_template(db, user_id, entry.template_id)  # type: ignore[arg-type]
        if template is None:
            raise BlockError("Тренировка не найдена в вашей библиотеке")
        items.append(
            BlockScheduleItem(
                day_index=entry.day_index,
                kind="workout",
                name=template.name,
                template_id=template.id,
                snapshot=snapshot_from_template(template),
            )
        )
    return items


async def create_block(db: AsyncSession, user_id: uuid.UUID, data: BlockInput) -> Block:
    """Сохраняет блок. Если разгрузки нет, добавляет её с объёмом 50% и RIR 4."""
    try:
        weeks = with_default_deload(_specs(data.weeks))
    except DeloadRoomError as exc:
        raise BlockError(str(exc)) from None
    schedule = await _build_schedule(db, user_id, data.schedule)
    block = Block(
        user_id=user_id,
        name=data.name,
        length_weeks=len(weeks),
        cycle_days=data.cycle_days,
        weeks=_build_weeks(weeks),
        schedule=schedule,
    )
    db.add(block)
    await db.flush()
    return block


async def replace_block(
    db: AsyncSession, user_id: uuid.UUID, block: Block, data: BlockInput
) -> Block:
    """Заменяет название, недели и расписание. Уже применённые размещения не меняются."""
    schedule = await _build_schedule(db, user_id, data.schedule)
    block.name = data.name
    block.length_weeks = len(data.weeks)
    block.cycle_days = data.cycle_days
    # Сначала удаляем старые строки: у недель и дней расписания уникальные номера.
    block.weeks.clear()
    block.schedule.clear()
    await db.flush()
    block.weeks.extend(_build_weeks(_specs(data.weeks)))
    block.schedule.extend(schedule)
    await db.flush()
    return block


async def copy_block(db: AsyncSession, user_id: uuid.UUID, source: Block) -> Block:
    suffix_room = NAME_MAX - len(COPY_SUFFIX)
    copy = Block(
        user_id=user_id,
        name=source.name[:suffix_room] + COPY_SUFFIX,
        length_weeks=source.length_weeks,
        cycle_days=source.cycle_days,
        weeks=[
            BlockWeek(
                position=week.position,
                week_type=week.week_type,
                rep_min=week.rep_min,
                rep_max=week.rep_max,
                target_rir=week.target_rir,
                volume_multiplier=week.volume_multiplier,
            )
            for week in source.weeks
        ],
        schedule=[
            BlockScheduleItem(
                day_index=item.day_index,
                kind=item.kind,
                name=item.name,
                template_id=item.template_id,
                snapshot=list(item.snapshot),
            )
            for item in source.schedule
        ],
    )
    db.add(copy)
    await db.flush()
    return copy


def _weeks_snapshot(block: Block) -> list[dict]:
    return [
        {
            "position": week.position,
            "week_type": week.week_type,
            "rep_min": week.rep_min,
            "rep_max": week.rep_max,
            "target_rir": week.target_rir,
            "volume_multiplier": week.volume_multiplier,
        }
        for week in sorted(block.weeks, key=lambda item: item.position)
    ]


def _schedule_snapshot(block: Block) -> list[dict]:
    return [
        {
            "day_index": item.day_index,
            "kind": item.kind,
            "name": item.name,
            "items": list(item.snapshot),
        }
        for item in block.schedule
    ]


def _occupied_dates(
    start: dt.date,
    length_weeks: int,
    cycle_days: int,
    weeks: list[dict],
    schedule: list[dict],
    *,
    repeats: bool,
    window_end: dt.date,
) -> set[dt.date]:
    return {
        slot.date
        for slot in build_slots(
            uuid.uuid4(),
            start,
            length_weeks,
            weeks,
            schedule,
            cycle_days,
            repeats=repeats,
            window=(start, window_end),
        )
    }


async def _ensure_free(
    db: AsyncSession, user_id: uuid.UUID, start: dt.date, end: dt.date, planned_days: set[dt.date]
) -> None:
    existing = await list_entries(db, user_id, start, end)
    busy = sorted({entry.date for entry in existing if entry.date in planned_days})
    if busy:
        raise BlockConflictError(
            f"На {busy[0].isoformat()} уже есть план. Выберите другую дату старта "
            "или освободите дни."
        )


async def apply_block(
    db: AsyncSession,
    user_id: uuid.UUID,
    block: Block,
    start: dt.date,
    *,
    repeats: bool = False,
) -> BlockPlacement:
    """Ставит блок в календарь с датой старта. Занятый день любого блока отклоняет применение."""
    await _lock_user_plan(db, user_id)
    weeks = _weeks_snapshot(block)
    schedule = _schedule_snapshot(block)
    if repeats:
        end = None
        window_end = start + dt.timedelta(days=REPEAT_CONFLICT_DAYS)
    else:
        end = block_end(start, block.length_weeks, block.cycle_days)
        window_end = end
    planned_days = _occupied_dates(
        start,
        block.length_weeks,
        block.cycle_days,
        weeks,
        schedule,
        repeats=repeats,
        window_end=window_end,
    )
    await _ensure_free(db, user_id, start, window_end, planned_days)
    placement = BlockPlacement(
        user_id=user_id,
        block_id=block.id,
        name=block.name,
        length_weeks=block.length_weeks,
        cycle_days=block.cycle_days,
        repeats=repeats,
        start_date=start,
        end_date=end,
        weeks_snapshot=weeks,
        schedule_snapshot=schedule,
    )
    db.add(placement)
    await db.flush()
    return placement


async def list_placements(db: AsyncSession, user_id: uuid.UUID) -> list[BlockPlacement]:
    return await load_placements(db, user_id)


async def repeat_placement(db: AsyncSession, user_id: uuid.UUID, placement: BlockPlacement) -> None:
    """Снимает дату конца: те же циклы продолжаются по кругу."""
    if placement.repeats:
        return
    if placement.end_date is None:
        raise BlockError("У блока уже нет даты конца")
    await _lock_user_plan(db, user_id)
    nxt = placement.end_date + dt.timedelta(days=1)
    window_end = nxt + dt.timedelta(days=REPEAT_CONFLICT_DAYS)
    planned_days = _occupied_dates(
        placement.start_date,
        placement.length_weeks,
        placement.cycle_days,
        list(placement.weeks_snapshot),
        list(placement.schedule_snapshot),
        repeats=True,
        window_end=window_end,
    )
    planned_days = {day for day in planned_days if day >= nxt}
    await _ensure_free(db, user_id, nxt, window_end, planned_days)
    placement.repeats = True
    placement.end_date = None
    await db.flush()


async def remove_placement(db: AsyncSession, user_id: uuid.UUID, placement: BlockPlacement) -> None:
    """Снимает блок с календаря.

    Тренировки блока, которых ещё никто не трогал, исчезают. Отмеченные выполненными или
    пропущенными остаются обычными записями: это уже история.
    """
    await _lock_user_plan(db, user_id)
    await db.execute(
        delete(PlannedWorkout).where(
            PlannedWorkout.placement_id == placement.id,
            or_(PlannedWorkout.status.is_(None), PlannedWorkout.status == STATUS_PLANNED),
        )
    )
    await db.execute(
        update(PlannedWorkout)
        .where(PlannedWorkout.placement_id == placement.id)
        .values(placement_id=None, day_offset=None)
    )
    await db.delete(placement)
    await db.flush()
