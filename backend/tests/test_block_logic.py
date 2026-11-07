"""Чистые правила блока: слоты от даты старта и наложение параметров недели."""

import datetime as dt
import uuid

from app.services.block_rules import apply_week, block_end, build_slots, slot_id

PLACEMENT = uuid.UUID(int=7)
MON = dt.date(2026, 11, 2)


def _set(rep_min: int = 8, rep_max: int = 12, rir: int | None = 2) -> dict:
    return {"rep_min": rep_min, "rep_max": rep_max, "target_rir": rir, "rest_seconds": 90}


def _item(sets: int) -> dict:
    return {
        "position": 0,
        "exercise": {"exercise_id": str(uuid.UUID(int=1)), "name": "Жим"},
        "sets": [_set() for _ in range(sets)],
    }


def _week(position: int, *, rep_min: int, rep_max: int, rir: int, volume: float) -> dict:
    return {
        "position": position,
        "week_type": "hypertrophy",
        "rep_min": rep_min,
        "rep_max": rep_max,
        "target_rir": rir,
        "volume_multiplier": volume,
    }


def test_week_overrides_reps_and_rir_for_every_set() -> None:
    week = _week(1, rep_min=3, rep_max=5, rir=0, volume=1.0)
    [item] = apply_week([_item(2)], week)
    assert [(s["rep_min"], s["rep_max"], s["target_rir"]) for s in item["sets"]] == [
        (3, 5, 0),
        (3, 5, 0),
    ]


def test_volume_multiplier_keeps_a_share_of_sets_but_never_less_than_one() -> None:
    half = _week(1, rep_min=8, rep_max=12, rir=2, volume=0.5)
    assert len(apply_week([_item(3)], half)[0]["sets"]) == 2
    tiny = _week(1, rep_min=8, rep_max=12, rir=2, volume=0.1)
    assert len(apply_week([_item(3)], tiny)[0]["sets"]) == 1


def test_apply_week_does_not_touch_the_source_snapshot() -> None:
    items = [_item(2)]
    apply_week(items, _week(1, rep_min=1, rep_max=2, rir=0, volume=1.0))
    assert items[0]["sets"][0]["rep_min"] == 8


def test_slots_follow_schedule_days_and_week_parameters() -> None:
    weeks = [
        _week(1, rep_min=8, rep_max=12, rir=2, volume=1.0),
        _week(2, rep_min=3, rep_max=5, rir=0, volume=1.0),
    ]
    schedule = [
        {"day_index": 0, "kind": "workout", "name": "A", "items": [_item(2)]},
        {"day_index": 2, "kind": "rest", "name": None, "items": []},
    ]

    slots = build_slots(PLACEMENT, MON, 2, weeks, schedule)

    assert [(slot.date, slot.kind) for slot in slots] == [
        (dt.date(2026, 11, 2), "workout"),
        (dt.date(2026, 11, 4), "rest"),
        (dt.date(2026, 11, 9), "workout"),
        (dt.date(2026, 11, 11), "rest"),
    ]
    assert slots[0].items[0]["sets"][0]["rep_max"] == 12
    assert slots[2].items[0]["sets"][0]["rep_max"] == 5
    assert slots[1].items == []


def test_slot_ids_are_stable_and_unique_per_day() -> None:
    schedule = [{"day_index": 0, "kind": "rest", "name": None, "items": []}]
    first = build_slots(
        PLACEMENT, MON, 2, [_week(1, rep_min=1, rep_max=2, rir=0, volume=1.0)] * 2, schedule
    )
    again = build_slots(
        PLACEMENT,
        MON + dt.timedelta(days=60),
        2,
        [_week(1, rep_min=1, rep_max=2, rir=0, volume=1.0)] * 2,
        schedule,
    )
    assert [slot.id for slot in first] == [slot.id for slot in again]
    assert first[0].id == slot_id(PLACEMENT, 0)
    assert first[0].id != first[1].id


def test_six_day_cycle_keeps_the_rest_gap_into_the_deload() -> None:
    weeks = [
        {**_week(1, rep_min=8, rep_max=12, rir=2, volume=1.0), "week_type": "hypertrophy"},
        {**_week(2, rep_min=8, rep_max=12, rir=4, volume=0.5), "week_type": "deload"},
    ]
    schedule = []
    for index in range(6):
        if index % 2 == 0:
            schedule.append(
                {"day_index": index, "kind": "workout", "name": "A", "items": [_item(1)]}
            )
        else:
            schedule.append({"day_index": index, "kind": "rest", "name": None, "items": []})

    slots = build_slots(PLACEMENT, MON, 2, weeks, schedule, cycle_days=6)

    workouts = [slot for slot in slots if slot.kind == "workout"]
    assert [slot.date for slot in workouts] == [
        dt.date(2026, 11, 2),
        dt.date(2026, 11, 4),
        dt.date(2026, 11, 6),
        dt.date(2026, 11, 8),
        dt.date(2026, 11, 10),
        dt.date(2026, 11, 12),
    ]
    assert workouts[2].items[0]["sets"][0]["target_rir"] == 2
    assert workouts[3].items[0]["sets"][0]["target_rir"] == 4
    assert block_end(MON, 2, 6) == dt.date(2026, 11, 13)

    later = build_slots(
        PLACEMENT,
        MON,
        2,
        weeks,
        schedule,
        cycle_days=6,
        repeats=True,
        window=(dt.date(2026, 11, 14), dt.date(2026, 11, 19)),
    )
    later_workouts = [slot for slot in later if slot.kind == "workout"]
    assert [slot.date for slot in later_workouts] == [
        dt.date(2026, 11, 14),
        dt.date(2026, 11, 16),
        dt.date(2026, 11, 18),
    ]
    assert later_workouts[0].items[0]["sets"][0]["target_rir"] == 2
    assert later_workouts[0].day_offset == 12


def test_block_end_is_the_last_day_of_whole_weeks() -> None:
    assert block_end(MON, 1) == dt.date(2026, 11, 8)
    assert block_end(MON, 4) == dt.date(2026, 11, 29)
