import datetime as dt

from app.services.volume import build_groups, target_status, week_bounds


def test_monday_and_sunday_share_one_week() -> None:
    monday = dt.date(2026, 11, 2)
    sunday = dt.date(2026, 11, 8)
    next_monday = dt.date(2026, 11, 9)

    assert week_bounds(monday) == (monday, sunday)
    assert week_bounds(sunday) == (monday, sunday)
    assert week_bounds(next_monday) == (next_monday, dt.date(2026, 11, 15))


def test_status_bounds_are_inclusive() -> None:
    assert target_status(9) == "below"
    assert target_status(10) == "in_range"
    assert target_status(20) == "in_range"
    assert target_status(21) == "above"


def test_groups_are_sorted_by_sets_and_skip_empty() -> None:
    groups = build_groups([("back", 4), ("chest", 12), ("core", 0), ("legs", 0)])
    assert [group.muscle for group in groups] == ["chest", "back"]
    assert [group.status for group in groups] == ["in_range", "below"]
    assert groups[0].target_min == 10
    assert groups[0].target_max == 20


def test_no_group_has_no_target() -> None:
    groups = build_groups([(None, 3), ("chest", 25)])
    assert [group.muscle for group in groups] == ["chest", None]
    no_group = groups[1]
    assert no_group.target_min is None
    assert no_group.target_max is None
    assert no_group.status is None
