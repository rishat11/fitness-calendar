"""Правило границ блока при сдвиге (см. docstring app/services/plan_shift.py)."""

import datetime as dt
import uuid

import pytest
from app.services.block_calendar import PlacementSpan
from app.services.plan_shift import ShiftEntry, ShiftError, compute_shift

PLACEMENT = uuid.UUID(int=100)
NOV2 = dt.date(2026, 11, 2)
NOV3 = dt.date(2026, 11, 3)
NOV4 = dt.date(2026, 11, 4)
NOV9 = dt.date(2026, 11, 9)
NOV15 = dt.date(2026, 11, 15)


def _slot(number: int, day: dt.date, *, kind: str = "workout") -> ShiftEntry:
    return ShiftEntry(
        id=uuid.UUID(int=number),
        date=day,
        kind=kind,
        status="planned" if kind == "workout" else None,
        is_fixed=False,
        position=0,
        name=None if kind == "rest" else f"Тренировка {number}",
        placement_id=PLACEMENT,
        day_offset=number,
        virtual=True,
    )


def _row(number: int, day: dt.date, *, kind: str = "workout", fixed: bool = False) -> ShiftEntry:
    return ShiftEntry(
        id=uuid.UUID(int=number),
        date=day,
        kind=kind,
        status="planned" if kind == "workout" else None,
        is_fixed=fixed,
        position=0,
        name=None if kind == "rest" else f"Строка {number}",
    )


def _span(start: dt.date = NOV2, end: dt.date = NOV15) -> PlacementSpan:
    return PlacementSpan(id=PLACEMENT, name="Гипертрофия", start=start, end=end)


def test_shifting_from_the_block_start_moves_the_whole_block_without_rows() -> None:
    first, rest, third = _slot(1, NOV2), _slot(2, NOV4, kind="rest"), _slot(3, NOV9)
    plan = compute_shift(
        [first, rest, third],
        operation="shift_following",
        anchor_id=first.id,
        days=1,
        resolution="cascade",
        placements=[_span()],
    )

    [block] = plan.blocks
    assert (block.start_after, block.end_after) == (dt.date(2026, 11, 3), dt.date(2026, 11, 16))
    assert block.absorbed is True
    assert {change.id: change.date_after for change in plan.changes} == {
        first.id: NOV3,
        rest.id: dt.date(2026, 11, 5),
        third.id: dt.date(2026, 11, 10),
    }


def test_open_block_shifts_only_from_its_first_day() -> None:
    first, later = _slot(1, NOV2), _slot(3, NOV9)
    plan = compute_shift(
        [first, later],
        operation="shift_following",
        anchor_id=first.id,
        days=1,
        resolution="cascade",
        placements=[PlacementSpan(id=PLACEMENT, name="Гипертрофия", start=NOV2, end=None)],
    )

    [block] = plan.blocks
    assert block.start_after == NOV3
    assert block.end_after is None

    with pytest.raises(ShiftError, match="без конца"):
        compute_shift(
            [first, later],
            operation="shift_following",
            anchor_id=later.id,
            days=1,
            resolution="cascade",
            placements=[PlacementSpan(id=PLACEMENT, name="Гипертрофия", start=NOV2, end=None)],
        )


def test_shifting_inside_the_block_moves_only_its_end() -> None:
    first, third = _slot(1, NOV2), _slot(3, NOV9)
    plan = compute_shift(
        [first, third],
        operation="shift_following",
        anchor_id=third.id,
        days=2,
        resolution="cascade",
        placements=[_span()],
    )

    [block] = plan.blocks
    assert (block.start_before, block.start_after) == (NOV2, NOV2)
    assert block.end_after == dt.date(2026, 11, 17)
    assert block.absorbed is False
    assert [change.id for change in plan.changes] == [third.id]


def test_shift_only_leaves_the_block_boundaries_alone() -> None:
    first, third = _slot(1, NOV2), _slot(3, NOV9)
    plan = compute_shift(
        [first, third],
        operation="shift_only",
        anchor_id=third.id,
        days=1,
        resolution="cascade",
        placements=[_span()],
    )
    assert plan.blocks == ()


def test_block_before_the_anchor_keeps_its_boundaries() -> None:
    early_slot = _slot(1, NOV2)
    later_row = _row(2, NOV9)
    plan = compute_shift(
        [early_slot, later_row],
        operation="shift_following",
        anchor_id=later_row.id,
        days=1,
        placements=[_span(end=NOV4)],
    )
    assert plan.blocks == ()


def test_shift_that_would_empty_the_block_is_refused() -> None:
    anchor = _row(1, NOV3)
    with pytest.raises(ShiftError) as caught:
        compute_shift(
            [anchor],
            operation="shift_following",
            anchor_id=anchor.id,
            days=-20,
            resolution="cascade",
            placements=[_span()],
        )
    assert "Гипертрофия" in str(caught.value)


def test_uneven_shift_is_not_absorbed_so_the_block_must_materialize() -> None:
    first, third = _slot(1, NOV2), _slot(3, NOV9)
    stayer = _row(2, NOV3, kind="rest", fixed=True)
    plan = compute_shift(
        [first, stayer, third],
        operation="shift_following",
        anchor_id=first.id,
        days=1,
        resolution="cascade",
        placements=[_span()],
    )

    [block] = plan.blocks
    assert block.start_after == NOV3
    assert block.absorbed is False
    moved = {change.id: change.date_after for change in plan.changes}
    assert moved[first.id] == dt.date(2026, 11, 4)
    assert moved[third.id] == dt.date(2026, 11, 10)
