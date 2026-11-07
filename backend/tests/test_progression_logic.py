import datetime as dt
import uuid

import pytest
from app.services.progression import (
    MESSAGE_CONTINUE,
    MESSAGE_INCREASE,
    MESSAGE_STAGNATION,
    SessionInput,
    SetInput,
    TargetInput,
    WeekKind,
    progression_hint,
    week_type_for_offset,
)

TARGET = (TargetInput(8, 12, 2),)


def _set(**kwargs: object) -> SetInput:
    data: dict[str, object] = {
        "position": 0,
        "weight": 100.0,
        "extra_weight": None,
        "reps": 8,
        "rir": 2,
        "is_warmup": False,
        "is_assisted": False,
        "is_negative": False,
        "weight_type": "standard",
        "weight_step": 2.5,
        "weight_unit": "kg",
    }
    data.update(kwargs)
    return SetInput(**data)  # type: ignore[arg-type]


def _session(
    day: int,
    sets: list[SetInput],
    *,
    targets: tuple[TargetInput, ...] = TARGET,
    hour: int = 10,
    logged_on: dt.date | None = None,
    week_type: WeekKind | None = None,
) -> SessionInput:
    workout_day = dt.date(2026, 11, day)
    started = logged_on or workout_day
    return SessionInput(
        id=uuid.uuid4(),
        date=workout_day,
        started_at=dt.datetime(started.year, started.month, started.day, hour, tzinfo=dt.UTC),
        targets=targets,
        sets=tuple(sets),
        week_type=week_type,
    )


def _hint(sessions: list[SessionInput], *, rep_min: int = 8, rep_max: int = 12):
    return progression_hint(sessions, catalog_rep_min=rep_min, catalog_rep_max=rep_max)


def test_top_of_range_and_enough_rir_suggests_the_next_weight() -> None:
    session = _session(
        1,
        [
            _set(position=0, weight=100, reps=12, rir=2),
            _set(position=1, weight=100, reps=12, rir=3),
        ],
    )

    hint = _hint([session])

    assert hint is not None
    assert hint.status == "increase_weight"
    assert hint.message == MESSAGE_INCREASE
    assert hint.suggested_weight == 102.5
    assert hint.last_session_id == session.id
    assert hint.epley_1rm == 140
    assert hint.week_type is None
    # Запас ровно в цель ещё годится. Ниже цели вес не предлагаем.
    short = _session(1, [_set(reps=12, rir=1)])
    assert _hint([short]) is None
    # Пустой снимок берёт диапазон справочника. Целевой RIR не задан — условие выполнено.
    from_catalog = _session(2, [_set(reps=10, rir=None)], targets=())
    catalog = _hint([from_catalog], rep_max=10)
    assert catalog is not None
    assert catalog.status == "increase_weight"
    assert catalog.suggested_weight == 102.5


def test_more_reps_inside_the_range_says_to_continue() -> None:
    first = _session(1, [_set(reps=8)])
    second = _session(3, [_set(reps=10)])

    hint = _hint([second, first])

    assert hint is not None
    assert hint.status == "continue"
    assert hint.message == MESSAGE_CONTINUE
    assert hint.suggested_weight is None
    assert hint.last_session_id == second.id
    assert hint.epley_1rm == round(100 * (1 + 10 / 30), 2)
    assert hint.week_type is None


def test_three_flat_sessions_are_stagnation() -> None:
    first = _session(1, [_set(reps=8)])
    second = _session(3, [_set(reps=8)])
    assert _hint([first, second]) is None

    hint = _hint([first, second, _session(5, [_set(reps=8)])])

    assert hint is not None
    assert hint.status == "stagnation"
    assert hint.message == MESSAGE_STAGNATION
    assert "5–10%" in hint.message
    assert hint.suggested_weight is None
    assert hint.week_type is None


def test_falling_reps_and_load_over_three_sessions_is_stagnation() -> None:
    first = _session(1, [_set(weight=100, reps=10)])
    second = _session(3, [_set(weight=90, reps=8)])
    # Двух сессий для стагнации мало, даже если и вес, и повторы упали.
    assert _hint([first, second]) is None

    hint = _hint([first, second, _session(5, [_set(weight=80, reps=6)])])

    assert hint is not None
    assert hint.status == "stagnation"
    assert hint.message == MESSAGE_STAGNATION


def test_warmup_assistance_and_negatives_do_not_count() -> None:
    only_warmup = _session(1, [_set(weight=200, reps=15, is_warmup=True)])
    assert _hint([only_warmup]) is None

    session = _session(
        2,
        [
            _set(position=0, weight=200, reps=15, rir=0, is_warmup=True),
            _set(position=1, weight=200, reps=15, rir=0, is_assisted=True),
            _set(position=2, weight=None, reps=12),
            _set(position=3, weight=100, reps=12, rir=2),
            _set(position=4, weight=20, reps=1, rir=0, is_negative=True),
        ],
    )

    hint = _hint([session])

    assert hint is not None
    assert hint.status == "increase_weight"
    assert hint.suggested_weight == 102.5
    assert hint.epley_1rm == 140


def test_assisted_machine_does_not_propose_a_weight() -> None:
    top = _set(weight_type="bodyweight_assisted", weight=40, reps=12, rir=3, weight_step=5)
    assert _hint([_session(1, [top])]) is None

    earlier = _set(weight_type="bodyweight_assisted", weight=40, reps=8, rir=3, weight_step=5)
    later = _set(weight_type="bodyweight_assisted", weight=40, reps=10, rir=3, weight_step=5)
    hint = _hint([_session(1, [earlier]), _session(3, [later])])

    assert hint is not None
    assert hint.status == "continue"
    assert hint.suggested_weight is None
    assert hint.epley_1rm is None


def test_calendar_date_orders_sessions_before_the_clock() -> None:
    """Дата тренировки важнее момента записи: задним числом не обгоняет более поздний день."""
    logged_late = _session(
        1,
        [_set(reps=12, rir=2)],
        logged_on=dt.date(2026, 11, 7),
        hour=18,
    )
    later_day = _session(5, [_set(reps=8)], hour=8)

    assert _hint([logged_late, later_day]) is None


def _typed(
    day: int,
    reps: int,
    *,
    weight: float = 100,
    week_type: WeekKind | None = None,
    rep_min: int = 8,
    rep_max: int = 12,
    rir: int = 2,
) -> SessionInput:
    return _session(
        day,
        [_set(weight=weight, reps=reps, rir=rir)],
        targets=(TargetInput(rep_min, rep_max, 2),),
        week_type=week_type,
    )


@pytest.mark.parametrize(
    ("sessions", "status", "week_type"),
    [
        pytest.param(
            [
                _typed(1, 8, week_type="hypertrophy"),
                _typed(3, 12, week_type="deload"),
                _typed(5, 10, week_type="hypertrophy"),
            ],
            "continue",
            "hypertrophy",
            id="deload-between-same-type-is-not-the-baseline",
        ),
        pytest.param(
            [
                _typed(1, 12, week_type="high_reps", weight=90, rir=2),
                _typed(3, 8, week_type="hypertrophy"),
            ],
            None,
            None,
            id="heavier-other-type-is-not-progress",
        ),
        pytest.param(
            [
                _typed(1, 8, week_type="hypertrophy"),
                _typed(3, 9, week_type="hypertrophy"),
                _typed(5, 8, week_type="high_reps", weight=100),
                _typed(7, 8, week_type="hypertrophy"),
            ],
            None,
            None,
            id="other-type-does-not-create-stagnation",
        ),
        pytest.param(
            [
                _typed(1, 8, week_type="strength"),
                _typed(3, 8, week_type="strength"),
                _typed(5, 8, week_type="strength"),
            ],
            "stagnation",
            "strength",
            id="three-flat-weeks-of-one-type",
        ),
        pytest.param(
            [_typed(1, 5, week_type="deload", weight=60, rep_min=3, rep_max=5, rir=3)],
            None,
            None,
            id="deload-at-the-top-does-not-raise-weight",
        ),
        pytest.param(
            [
                _typed(1, 4, week_type="deload", weight=60, rep_min=3, rep_max=5),
                _typed(3, 5, week_type="deload", weight=60, rep_min=3, rep_max=5, rir=3),
            ],
            None,
            None,
            id="deload-reaching-the-top-is-still-not-an-increase",
        ),
        pytest.param(
            [
                _typed(1, 3, week_type="deload", weight=60, rep_min=3, rep_max=5),
                _typed(3, 4, week_type="deload", weight=60, rep_min=3, rep_max=5),
            ],
            "continue",
            "deload",
            id="deload-below-the-top-still-compares-with-deload",
        ),
        pytest.param(
            [
                _typed(1, 12, week_type="hypertrophy", rir=2),
                _typed(3, 5, week_type="deload", weight=60, rep_min=3, rep_max=5, rir=3),
            ],
            None,
            None,
            id="deload-after-a-top-week-does-not-inherit-its-increase",
        ),
    ],
)
def test_week_type_decision_table(
    sessions: list[SessionInput], status: str | None, week_type: str | None
) -> None:
    """Сравнение только внутри типа последней сессии. Разгрузка не точка прибавки веса."""
    hint = _hint(sessions)

    if status is None:
        assert hint is None
        return
    assert hint is not None
    assert hint.status == status
    assert hint.week_type == week_type
    assert hint.suggested_weight is None


def test_sessions_outside_a_block_keep_the_old_comparison() -> None:
    """Тренировка без типа сравнивается только с такими же, неделя блока её не двигает.

    Рост повторов по-прежнему «продолжайте», три ровных — стагнация, верх диапазона —
    повысить вес. Тип в подсказке пустой: это прежнее поведение вне блока.
    """
    grew = _hint(
        [
            _typed(1, 8),
            _typed(3, 12, week_type="hypertrophy", weight=110, rir=2),
            _typed(5, 10),
        ]
    )
    assert grew is not None
    assert grew.status == "continue"
    assert grew.week_type is None
    assert grew.suggested_weight is None

    stuck = _hint(
        [
            _typed(1, 8),
            _typed(3, 8),
            _typed(5, 12, week_type="strength", weight=140, rir=2),
            _typed(7, 8),
        ]
    )
    assert stuck is not None
    assert stuck.status == "stagnation"
    assert stuck.week_type is None

    raised = _hint([_typed(1, 6, week_type="high_reps", weight=40), _typed(3, 12, rir=2)])
    assert raised is not None
    assert raised.status == "increase_weight"
    assert raised.week_type is None
    assert raised.suggested_weight == 102.5


def test_week_type_comes_from_the_block_day_offset() -> None:
    weeks = (
        {"week_type": "hypertrophy"},
        {"week_type": "deload"},
        {"week_type": "free"},
    )

    assert week_type_for_offset(0, weeks) == "hypertrophy"
    assert week_type_for_offset(6, weeks) == "hypertrophy"
    assert week_type_for_offset(7, weeks) == "deload"
    assert week_type_for_offset(5, weeks, cycle_days=6) == "hypertrophy"
    assert week_type_for_offset(6, weeks, cycle_days=6) == "deload"
    assert week_type_for_offset(14, weeks) == "free"
    assert week_type_for_offset(21, weeks) is None
    assert week_type_for_offset(21, weeks, repeats=True) == "hypertrophy"
    assert week_type_for_offset(None, weeks) is None
    assert week_type_for_offset(0, ()) is None
    assert week_type_for_offset(0, ({"week_type": "other"},)) is None
