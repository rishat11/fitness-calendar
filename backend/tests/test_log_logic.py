import uuid

from app.models.log import PerformedItem, SetLog
from app.services.log import set_load, summarize


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


def _item(weight_type: str, sets: list[SetLog], unit: str = "kg") -> PerformedItem:
    item = PerformedItem(
        id=uuid.uuid4(),
        performed_id=uuid.uuid4(),
        position=0,
        name="Упражнение",
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
