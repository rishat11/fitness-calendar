import uuid

from app.models.log import PerformedItem, SetLog
from app.services.log import records_against, set_load, summarize


def _set(**kwargs: object) -> SetLog:
    data: dict[str, object] = {
        "id": uuid.uuid4(),
        "item_id": uuid.uuid4(),
        "performed_id": uuid.uuid4(),
        "position": 0,
        "is_warmup": False,
        "is_assisted": False,
        "is_negative": False,
    }
    data.update(kwargs)
    return SetLog(**data)


def _item(
    weight_type: str,
    sets: list[SetLog],
    unit: str = "kg",
    *,
    exercise_id: uuid.UUID | None = None,
    name: str = "Упражнение",
) -> PerformedItem:
    item = PerformedItem(
        id=uuid.uuid4(),
        performed_id=uuid.uuid4(),
        position=0,
        exercise_id=exercise_id,
        name=name,
        equipment="barbell",
        weight_type=weight_type,
        weight_unit=unit,
        weight_step=2.5,
    )
    item.sets = sets
    return item


def test_load_depends_on_weight_type() -> None:
    assert set_load("standard", 80, None) == 80
    assert set_load("per_dumbbell", 24, None) == 48
    assert set_load("stack_plus_extra", 40, 2.5) == 42.5
    assert set_load("stack_plus_extra", None, 5) == 5
    assert set_load("bodyweight_plus", 10, None) == 10
    assert set_load("bodyweight_assisted", 40, None) is None
    assert set_load("standard", None, None) is None


def test_summary_skips_warmup_and_empty_sets() -> None:
    item = _item(
        "standard",
        [
            _set(position=0, weight=60, reps=12, is_warmup=True),
            _set(position=1, weight=100, reps=8),
            _set(position=2, weight=100, reps=None),
        ],
    )

    summary = summarize([item])

    assert summary.working_sets == 1
    assert summary.volume == 800
    assert summary.unit == "kg"


def test_summary_mixes_units_without_pretending_they_match() -> None:
    bar = _item("per_dumbbell", [_set(weight=20, reps=10)])
    cable = _item("stack_plus_extra", [_set(weight=50, reps=8, extra_weight=5)], unit="lb")

    summary = summarize([bar, cable])

    # 20 кг × 2 × 10 + (50 + 5) lb × 8 — единицы разные, объём остаётся суммой чисел.
    assert summary.working_sets == 2
    assert summary.volume == 840
    assert summary.unit is None


def test_assisted_set_counts_without_volume() -> None:
    item = _item("bodyweight_assisted", [_set(weight=35, reps=6, is_assisted=False)])

    summary = summarize([item])

    assert summary.working_sets == 1
    assert summary.volume == 0
    assert summary.unit is None


def test_first_session_sets_three_records() -> None:
    exercise_id = uuid.uuid4()
    item = _item(
        "standard",
        [_set(position=0, weight=60, reps=12), _set(position=1, weight=100, reps=3)],
        exercise_id=exercise_id,
        name="Жим",
    )

    records = records_against([item], [])

    assert [record.kind for record in records] == ["weight", "reps", "epley"]
    assert records[0].load == 100
    assert records[0].name == "Жим"
    assert records[1].reps == 12
    assert records[1].load == 60
    # 1ПМ берётся у подхода 100×3, а не у более многоповторного 60×12.
    assert records[2].epley_1rm == round(100 * (1 + 3 / 30), 2)
    assert records[2].load == 100


def test_heavier_load_is_a_record_and_a_tie_is_not() -> None:
    exercise_id = uuid.uuid4()
    earlier = _item("standard", [_set(weight=100, reps=10)], exercise_id=exercise_id)
    heavier = _item("standard", [_set(weight=110, reps=2)], exercise_id=exercise_id)
    same = _item("standard", [_set(weight=100, reps=10)], exercise_id=exercise_id)

    improved = records_against([heavier], [earlier])

    assert [record.kind for record in improved] == ["weight"]
    assert improved[0].load == 110
    assert records_against([same], [earlier]) == []


def test_more_reps_at_the_same_load() -> None:
    exercise_id = uuid.uuid4()
    earlier = _item("standard", [_set(weight=100, reps=5)], exercise_id=exercise_id)
    current = _item("standard", [_set(weight=100, reps=8)], exercise_id=exercise_id)

    records = records_against([current], [earlier])

    assert [record.kind for record in records] == ["reps", "epley"]
    assert records[0].reps == 8
    assert records[0].load == 100
    assert records[1].epley_1rm == round(100 * (1 + 8 / 30), 2)


def test_better_epley_without_a_new_max_load() -> None:
    exercise_id = uuid.uuid4()
    earlier = _item("standard", [_set(weight=100, reps=5)], exercise_id=exercise_id)
    current = _item("standard", [_set(weight=90, reps=10)], exercise_id=exercise_id)

    records = records_against([current], [earlier])

    assert [record.kind for record in records] == ["epley"]
    assert records[0].load == 90
    assert records[0].epley_1rm == round(90 * (1 + 10 / 30), 2)


def test_warmup_assisted_and_negatives_do_not_count() -> None:
    exercise_id = uuid.uuid4()
    earlier = _item("standard", [_set(weight=100, reps=5)], exercise_id=exercise_id)
    current = _item(
        "standard",
        [
            _set(position=0, weight=200, reps=10, is_warmup=True),
            _set(position=1, weight=200, reps=10, is_assisted=True),
            _set(position=2, weight=200, reps=10, is_negative=True),
            _set(position=3, weight=80, reps=5),
        ],
        exercise_id=exercise_id,
    )

    assert records_against([current], [earlier]) == []
    warmup_only = _item(
        "standard", [_set(weight=200, reps=10, is_warmup=True)], exercise_id=exercise_id
    )
    assert records_against([warmup_only], []) == []


def test_assisted_machine_has_reps_record_without_weight() -> None:
    exercise_id = uuid.uuid4()
    first = _item("bodyweight_assisted", [_set(weight=40, reps=8)], exercise_id=exercise_id)
    opened = records_against([first], [])

    assert [record.kind for record in opened] == ["reps"]
    assert opened[0].load is None
    assert opened[0].reps == 8
    assert opened[0].epley_1rm is None

    lighter_help = _item("bodyweight_assisted", [_set(weight=20, reps=6)], exercise_id=exercise_id)
    assert records_against([lighter_help], [first]) == []

    more_reps = _item("bodyweight_assisted", [_set(weight=50, reps=10)], exercise_id=exercise_id)
    again = records_against([more_reps], [first])
    assert [record.kind for record in again] == ["reps"]
    assert again[0].reps == 10
    assert again[0].load is None


def test_dumbbell_and_stack_records_use_set_load() -> None:
    dumbbell = uuid.uuid4()
    earlier_bell = _item("per_dumbbell", [_set(weight=20, reps=8)], exercise_id=dumbbell)
    current_bell = _item("per_dumbbell", [_set(weight=24, reps=5)], exercise_id=dumbbell)
    bell = records_against([current_bell], [earlier_bell])
    assert bell[0].kind == "weight"
    assert bell[0].load == 48

    stack = uuid.uuid4()
    earlier_stack = _item(
        "stack_plus_extra", [_set(weight=40, extra_weight=0, reps=8)], exercise_id=stack
    )
    current_stack = _item(
        "stack_plus_extra", [_set(weight=40, extra_weight=5, reps=8)], exercise_id=stack
    )
    added = records_against([current_stack], [earlier_stack])
    assert [record.kind for record in added] == ["weight", "epley"]
    assert added[0].load == 45


def test_another_exercise_does_not_set_the_bar() -> None:
    bench = uuid.uuid4()
    row = uuid.uuid4()
    earlier = _item("standard", [_set(weight=200, reps=5)], exercise_id=bench)
    current = _item("standard", [_set(weight=40, reps=8)], exercise_id=row, name="Тяга")

    records = records_against([current], [earlier])

    assert [record.kind for record in records] == ["weight", "reps", "epley"]
    assert records[0].load == 40
    assert records[0].name == "Тяга"
