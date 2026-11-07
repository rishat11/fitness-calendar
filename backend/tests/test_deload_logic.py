"""Таблица решений: когда предлагать разгрузку раньше плана и какая неделя ставится по умолчанию."""

import uuid

import pytest
from app.models.block import MAX_BLOCK_WEEKS
from app.services.deload import (
    DEFAULT_DELOAD_RIR,
    DEFAULT_DELOAD_VOLUME,
    REASON_LOW_RIR,
    REASON_LOW_WELLBEING,
    REASON_REP_DROP,
    REASON_SKIPS,
    REASON_STAGNATION,
    DeloadRoomError,
    ExerciseWeek,
    WeekRecord,
    WeekSpec,
    suggest_early_deload,
    with_default_deload,
)

A = uuid.UUID(int=1)
B = uuid.UUID(int=2)


def _point(exercise: uuid.UUID, reps: int | None, rir: int | None) -> ExerciseWeek:
    return ExerciseWeek(exercise, reps, rir)


def _week(*points: ExerciseWeek, skipped: int = 0, wellbeing: int | None = None) -> WeekRecord:
    return WeekRecord(points, skipped, wellbeing)


@pytest.mark.parametrize(
    ("weeks", "target", "needed", "reasons"),
    [
        pytest.param([], "hypertrophy", False, (), id="empty-history"),
        pytest.param(
            [_week(_point(A, 8, 0), _point(B, 8, 1))],
            "hypertrophy",
            False,
            (REASON_LOW_RIR,),
            id="one-sign-is-not-enough",
        ),
        pytest.param(
            [_week(_point(A, 8, 0), skipped=2)],
            "hypertrophy",
            False,
            (REASON_SKIPS,),
            id="low-rir-needs-two-exercises",
        ),
        pytest.param(
            [_week(_point(A, 8, 0), _point(B, 8, 1), skipped=2)],
            "hypertrophy",
            True,
            (REASON_LOW_RIR, REASON_SKIPS),
            id="low-rir-and-skips-in-one-week",
        ),
        pytest.param(
            [
                _week(_point(A, 10, 3), _point(B, 12, 3)),
                _week(_point(A, 8, 0), _point(B, 9, 1)),
            ],
            "hypertrophy",
            True,
            (REASON_LOW_RIR, REASON_REP_DROP),
            id="rir-0-1-and-rep-drop-of-two",
        ),
        pytest.param(
            [
                _week(_point(A, 10, 3), _point(B, 12, 3)),
                _week(_point(A, 9, 0), _point(B, 11, 1)),
            ],
            "hypertrophy",
            False,
            (REASON_LOW_RIR,),
            id="drop-of-one-rep-does-not-count",
        ),
        pytest.param(
            [
                _week(_point(A, 10, 3), _point(B, 12, 2)),
                _week(_point(A, 8, 0), _point(B, 12, 2)),
            ],
            "strength",
            False,
            (),
            id="one-exercise-does-not-make-a-sign",
        ),
        pytest.param(
            [
                _week(_point(A, 10, 3), _point(B, 10, 3)),
                _week(_point(A, 8, 0), _point(B, 8, 0)),
            ],
            "deload",
            False,
            (REASON_LOW_RIR, REASON_REP_DROP),
            id="already-deload-is-not-early",
        ),
        pytest.param(
            [
                _week(_point(A, 8, 2), _point(B, 8, 2)),
                _week(_point(A, 8, 2), _point(B, 8, 2)),
                _week(_point(A, 8, 2), _point(B, 7, 2), wellbeing=2),
            ],
            "hypertrophy",
            True,
            (REASON_STAGNATION, REASON_LOW_WELLBEING),
            id="flat-reps-and-low-wellbeing",
        ),
        pytest.param(
            [
                _week(_point(A, 8, 2), _point(B, 8, 2)),
                _week(_point(A, 9, 2), _point(B, 8, 2)),
                _week(_point(A, 10, 2), _point(B, 9, 2)),
            ],
            "hypertrophy",
            False,
            (),
            id="rising-reps-are-not-stagnation",
        ),
        pytest.param(
            [_week(skipped=1, wellbeing=2)],
            "free",
            False,
            (REASON_LOW_WELLBEING,),
            id="one-skip-is-below-the-threshold",
        ),
        pytest.param(
            [_week(skipped=2, wellbeing=3)],
            "hypertrophy",
            False,
            (REASON_SKIPS,),
            id="wellbeing-3-is-not-low",
        ),
        pytest.param(
            [_week(skipped=1), _week(skipped=1, wellbeing=1)],
            "hypertrophy",
            True,
            (REASON_SKIPS, REASON_LOW_WELLBEING),
            id="skips-add-up-over-two-weeks",
        ),
        pytest.param(
            [_week(skipped=2), _week(skipped=0), _week(skipped=0)],
            "hypertrophy",
            False,
            (),
            id="old-skips-leave-the-window",
        ),
        pytest.param(
            [_week(wellbeing=0), _week(wellbeing=6)],
            "hypertrophy",
            False,
            (),
            id="wellbeing-outside-1-5-is-ignored",
        ),
        pytest.param(
            [
                _week(_point(A, 10, 3), _point(B, 10, 3)),
                _week(_point(A, 8, 0), _point(B, 8, 1)),
                _week(),
            ],
            "high_reps",
            True,
            (REASON_LOW_RIR, REASON_REP_DROP),
            id="empty-current-week-keeps-the-previous-training",
        ),
        pytest.param(
            [
                _week(_point(A, 8, 2), _point(B, 8, 2)),
                _week(),
                _week(_point(A, 8, 2), _point(B, 8, 2)),
                _week(_point(A, 8, 2), _point(B, 8, 2)),
            ],
            "hypertrophy",
            False,
            (REASON_STAGNATION,),
            id="empty-week-does-not-break-stagnation",
        ),
    ],
)
def test_early_deload_decision_table(
    weeks: list[WeekRecord], target: str, needed: bool, reasons: tuple[str, ...]
) -> None:
    decision = suggest_early_deload(weeks, target_week_type=target)

    assert decision.needed is needed
    assert decision.reasons == reasons


def test_duplicate_points_in_one_week_use_best_reps_and_lowest_rir() -> None:
    weeks = [_week(_point(A, 10, 3), _point(A, 6, 0), _point(B, 8, 4), _point(B, 8, 1))]

    decision = suggest_early_deload(weeks, target_week_type="hypertrophy")

    assert decision.reasons == (REASON_LOW_RIR,)
    assert decision.needed is False


def test_missing_deload_week_is_appended_with_half_volume() -> None:
    source = WeekSpec("strength", 3, 5, 1, 1.0)

    kept, added = with_default_deload([source])

    assert kept == source
    assert added == WeekSpec("deload", 3, 5, DEFAULT_DELOAD_RIR, DEFAULT_DELOAD_VOLUME)


def test_custom_deload_multiplier_is_left_alone() -> None:
    weeks = [
        WeekSpec("hypertrophy", 8, 12, 2, 1.0),
        WeekSpec("deload", 8, 12, 3, 0.6),
    ]

    assert with_default_deload(weeks) == weeks


def test_full_block_without_deload_is_not_truncated() -> None:
    weeks = [WeekSpec("hypertrophy", 8, 12, 2, 1.0) for _ in range(MAX_BLOCK_WEEKS)]

    with pytest.raises(DeloadRoomError):
        with_default_deload(weeks)


def test_full_block_that_already_has_deload_fits() -> None:
    weeks = [WeekSpec("hypertrophy", 8, 12, 2, 1.0) for _ in range(MAX_BLOCK_WEEKS - 1)]
    weeks.append(WeekSpec("deload", 6, 10, 3, 0.6))

    assert with_default_deload(weeks) == weeks
