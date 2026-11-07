"""Чистая функция сдвига: предпросмотр и применение обязаны считать одно и то же."""

import datetime as dt
import uuid

import pytest
from app.services.plan_shift import (
    RESOLUTION_CANCEL,
    RESOLUTION_CASCADE,
    ShiftEntry,
    ShiftError,
    compute_shift,
)

MON = dt.date(2026, 11, 2)
TUE = dt.date(2026, 11, 3)
WED = dt.date(2026, 11, 4)
THU = dt.date(2026, 11, 5)
FRI = dt.date(2026, 11, 6)
SAT = dt.date(2026, 11, 7)


def _entry(
    number: int,
    day: dt.date,
    *,
    kind: str = "workout",
    status: str | None = "planned",
    is_fixed: bool = False,
    position: int = 0,
    name: str | None = None,
) -> ShiftEntry:
    if kind == "rest":
        status = None
        name = None
    return ShiftEntry(
        id=uuid.UUID(int=number),
        date=day,
        kind=kind,
        status=status,
        is_fixed=is_fixed,
        position=position,
        name=name if name is not None else f"День {number}",
    )


def _dates(entries: list[ShiftEntry], **kwargs: object) -> dict[uuid.UUID, dt.date]:
    plan = compute_shift(entries, **kwargs)  # type: ignore[arg-type]
    return {change.id: change.date_after for change in plan.changes}


def test_shift_following_keeps_gaps_across_empty_days() -> None:
    monday = _entry(1, MON)
    friday = _entry(2, FRI)
    moved = _dates([monday, friday], operation="shift_following", anchor_id=monday.id, days=1)
    assert moved == {monday.id: TUE, friday.id: SAT}


def test_done_and_skipped_stay_while_planned_and_rest_move() -> None:
    monday = _entry(1, MON)
    rest = _entry(2, TUE, kind="rest")
    done = _entry(3, WED, status="done")
    later = _entry(4, THU)
    skipped = _entry(5, FRI, status="skipped")
    entries = [monday, rest, done, later, skipped]

    plan = compute_shift(entries, operation="shift_following", anchor_id=monday.id, days=1)

    assert {change.id for change in plan.changes} == {monday.id, rest.id, later.id}
    assert plan.conflicts
    assert "stack" not in plan.resolutions
    assert plan.resolutions == ("cascade", "cancel")

    cascaded = compute_shift(
        entries,
        operation="shift_following",
        anchor_id=monday.id,
        days=1,
        resolution="cascade",
    )
    assert {change.id: change.date_after for change in cascaded.changes} == {
        monday.id: TUE,
        rest.id: THU,
        later.id: SAT,
    }
    assert cascaded.conflicts == ()
    assert done.date == WED
    assert skipped.date == FRI


def test_fixed_rest_blocks_stacking_and_cascade_steps_over_it() -> None:
    monday = _entry(1, MON)
    fixed_rest = _entry(2, TUE, kind="rest", is_fixed=True)
    plan = compute_shift(
        entries := [monday, fixed_rest], operation="shift_only", anchor_id=monday.id, days=1
    )

    assert [conflict.reason for conflict in plan.conflicts] == ["blocked"]
    assert plan.resolutions == ("cascade", "cancel")

    stacked = compute_shift(
        entries, operation="shift_only", anchor_id=monday.id, days=1, resolution="stack"
    )
    assert stacked.conflicts
    assert "stack" not in stacked.resolutions

    cascaded = compute_shift(
        entries, operation="shift_only", anchor_id=monday.id, days=1, resolution="cascade"
    )
    assert {change.id: change.date_after for change in cascaded.changes} == {monday.id: WED}
    assert cascaded.conflicts == ()


def test_occupied_day_offers_stack_and_cascade() -> None:
    monday = _entry(1, MON)
    done = _entry(2, TUE, status="done")
    naive = compute_shift([monday, done], operation="shift_only", anchor_id=monday.id, days=1)
    assert [conflict.reason for conflict in naive.conflicts] == ["occupied"]
    assert naive.resolutions == ("cascade", "stack", "cancel")

    stacked = compute_shift(
        [monday, done], operation="shift_only", anchor_id=monday.id, days=1, resolution="stack"
    )
    assert stacked.conflicts == ()
    assert stacked.changes[0].date_after == TUE

    cascaded = compute_shift(
        [monday, done],
        operation="shift_only",
        anchor_id=monday.id,
        days=1,
        resolution="cascade",
    )
    assert cascaded.changes[0].date_after == WED
    assert cascaded.conflicts == ()


def test_cancel_moves_nothing() -> None:
    monday = _entry(1, MON)
    done = _entry(2, TUE, status="done")
    plan = compute_shift(
        [monday, done],
        operation="shift_only",
        anchor_id=monday.id,
        days=1,
        resolution=RESOLUTION_CANCEL,
    )
    assert plan.changes == ()
    assert plan.conflicts


def test_shift_only_leaves_the_following_entries() -> None:
    monday = _entry(1, MON)
    wednesday = _entry(2, WED)
    moved = _dates([monday, wednesday], operation="shift_only", anchor_id=monday.id, days=1)
    assert moved == {monday.id: TUE}


def test_rest_before_the_anchor_stays() -> None:
    earlier_rest = _entry(1, MON, kind="rest")
    wednesday = _entry(2, WED)
    later_rest = _entry(3, THU, kind="rest")
    moved = _dates(
        [earlier_rest, wednesday, later_rest],
        operation="shift_following",
        anchor_id=wednesday.id,
        days=1,
    )
    assert moved == {wednesday.id: THU, later_rest.id: FRI}


def test_fixed_workout_in_the_chain_stays() -> None:
    monday = _entry(1, MON)
    fixed = _entry(2, WED, is_fixed=True)
    friday = _entry(3, FRI)
    moved = _dates(
        [monday, fixed, friday], operation="shift_following", anchor_id=monday.id, days=1
    )
    assert moved == {monday.id: TUE, friday.id: SAT}


def test_same_day_done_workout_does_not_move_with_the_planned_one() -> None:
    planned = _entry(1, MON, position=0)
    done = _entry(2, MON, status="done", position=1)
    plan = compute_shift([planned, done], operation="shift_following", anchor_id=planned.id, days=1)
    assert {change.id for change in plan.changes} == {planned.id}
    assert plan.conflicts == ()
    assert plan.changes[0].date_after == TUE


def test_backward_cascade_keeps_order() -> None:
    done = _entry(1, TUE, status="done")
    wednesday = _entry(2, WED)
    thursday = _entry(3, THU)
    plan = compute_shift(
        [done, wednesday, thursday],
        operation="shift_following",
        anchor_id=wednesday.id,
        days=-1,
        resolution=RESOLUTION_CASCADE,
    )
    assert {change.id: change.date_after for change in plan.changes} == {
        wednesday.id: MON,
        thursday.id: WED,
    }


def test_skip_changes_status_only() -> None:
    monday = _entry(1, MON)
    wednesday = _entry(2, WED)
    plan = compute_shift([monday, wednesday], operation="skip", anchor_id=monday.id)
    [change] = plan.changes
    assert change.date_before == change.date_after == MON
    assert change.status_before == "planned"
    assert change.status_after == "skipped"
    assert plan.conflicts == ()


def test_swap_exchanges_dates() -> None:
    monday = _entry(1, MON, name="A")
    thursday = _entry(2, THU, name="B")
    plan = compute_shift(
        [monday, thursday], operation="swap", anchor_id=monday.id, other_id=thursday.id
    )
    assert {change.id: change.date_after for change in plan.changes} == {
        monday.id: THU,
        thursday.id: MON,
    }
    assert plan.conflicts == ()


def test_blocked_date_is_treated_as_a_boundary() -> None:
    """Граница блока (этап 3) не даёт встать на день и перешагивается цепочкой."""
    monday = _entry(1, MON)
    plan = compute_shift(
        [monday],
        operation="shift_only",
        anchor_id=monday.id,
        days=1,
        blocked_dates=frozenset({TUE}),
    )
    assert [conflict.reason for conflict in plan.conflicts] == ["blocked"]
    cascaded = compute_shift(
        [monday],
        operation="shift_only",
        anchor_id=monday.id,
        days=1,
        resolution=RESOLUTION_CASCADE,
        blocked_dates=frozenset({TUE}),
    )
    assert cascaded.changes[0].date_after == WED
    assert cascaded.conflicts == ()


@pytest.mark.parametrize(
    ("operation", "kwargs"),
    [
        ("shift_following", {"days": 1}),
        ("shift_only", {"days": 1}),
        ("skip", {}),
        ("swap", {"other_id": uuid.UUID(int=2)}),
    ],
)
def test_finished_workout_cannot_be_shifted(operation: str, kwargs: dict[str, object]) -> None:
    done = _entry(1, MON, status="done")
    other = _entry(2, WED)
    with pytest.raises(ShiftError):
        compute_shift([done, other], operation=operation, anchor_id=done.id, **kwargs)  # type: ignore[arg-type]


def test_missing_entry_is_an_error() -> None:
    with pytest.raises(ShiftError) as caught:
        compute_shift([], operation="shift_only", anchor_id=uuid.UUID(int=1), days=1)
    assert caught.value.missing
