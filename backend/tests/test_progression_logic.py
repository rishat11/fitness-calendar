import datetime as dt
import uuid

from app.services.progression import (
    MESSAGE_CONTINUE,
    MESSAGE_INCREASE,
    MESSAGE_STAGNATION,
    SessionInput,
    SetInput,
    TargetInput,
    progression_hint,
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
) -> SessionInput:
    workout_day = dt.date(2026, 11, day)
    started = logged_on or workout_day
    return SessionInput(
        id=uuid.uuid4(),
        date=workout_day,
        started_at=dt.datetime(started.year, started.month, started.day, hour, tzinfo=dt.UTC),
        targets=targets,
        sets=tuple(sets),
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
