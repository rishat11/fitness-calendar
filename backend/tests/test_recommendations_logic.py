from datetime import date, timedelta
from decimal import Decimal

from app.services.recommendations import (
    MAX_STEP_KCAL,
    STEP_KCAL,
    IntakeSnapshot,
    Recommendation,
    ScanSnapshot,
    recommend,
)

GOAL = "muscle_gain"
INTAKE = IntakeSnapshot(
    calories=Decimal("2500"),
    protein_g=Decimal("100"),
    fat_g=Decimal("80"),
    carbs_g=Decimal("300"),
)


def _scan(
    day: int,
    *,
    weight: str = "80",
    smm: str = "40",
    bfm: str = "12",
    pbf: str = "15",
    bmr: int = 1800,
) -> ScanSnapshot:
    return ScanSnapshot(
        measured_on=date(2026, 10, 1) + timedelta(days=day),
        weight_kg=Decimal(weight),
        smm_kg=Decimal(smm),
        bfm_kg=Decimal(bfm),
        pbf_percent=Decimal(pbf),
        bmr_kcal=bmr,
    )


def _codes(items: list[Recommendation]) -> list[str]:
    return [item.code for item in items]


def _by_code(items: list[Recommendation], code: str) -> Recommendation:
    found = [item for item in items if item.code == code]
    assert len(found) == 1
    return found[0]


def test_step_stays_inside_the_ceiling() -> None:
    assert STEP_KCAL == 200
    assert STEP_KCAL <= MAX_STEP_KCAL


def test_growing_muscle_and_stable_fat_keeps_calories() -> None:
    items = recommend(
        goal=GOAL,
        sex="male",
        intake=INTAKE,
        scans=[
            _scan(0, smm="40", bfm="12", weight="80"),
            _scan(14, smm="40.2", bfm="12", weight="80.1"),
            _scan(28, smm="40.6", bfm="11.9", weight="80.2"),
        ],
    )
    trend = _by_code(items, "trend_keep")
    assert "не нужно" in trend.text
    assert "200" not in trend.text
    assert _codes(items).index("low_protein") < _codes(items).index("trend_keep")


def test_stall_on_muscle_gain_adds_one_step_from_carbs() -> None:
    scans = [
        _scan(0),
        _scan(14, weight="80.1", smm="40.1", bfm="12.1"),
        _scan(28, weight="80.2", smm="40.2", bfm="12.1"),
    ]
    items = recommend(goal=GOAL, sex="male", intake=INTAKE, scans=scans)
    trend = _by_code(items, "trend_surplus")
    assert f"{STEP_KCAL}" in trend.text
    assert "углевод" in trend.text
    assert "400" not in trend.text
    assert "300" not in trend.text
    assert _by_code(items, "trend_surplus").basis[-2].value == "200"
    again = recommend(goal=GOAL, sex="male", intake=INTAKE, scans=scans)
    assert [item.text for item in again] == [item.text for item in items]


def test_fat_gaining_faster_than_muscle_reduces_by_one_step() -> None:
    items = recommend(
        goal="maintenance",
        sex="male",
        intake=INTAKE,
        scans=[
            _scan(0, smm="40", bfm="12", weight="80"),
            _scan(10, smm="40", bfm="12.4", weight="80.4"),
            _scan(21, smm="40.2", bfm="13.0", weight="80.6"),
        ],
    )
    trend = _by_code(items, "trend_reduce")
    assert trend.basis[-1].label == "Откуда калории"
    assert "не среднее" in trend.basis[-1].value
    assert sum(code.startswith("trend_") for code in _codes(items)) == 1


def test_fast_weight_gain_reduces_even_when_muscle_is_up() -> None:
    items = recommend(
        goal=GOAL,
        sex="male",
        intake=INTAKE,
        scans=[
            _scan(0, weight="80", smm="40", bfm="12"),
            _scan(10, weight="80.6", smm="40.2", bfm="12"),
            _scan(21, weight="81.5", smm="40.5", bfm="12.1"),
        ],
    )
    assert "trend_reduce" in _codes(items)
    assert "trend_keep" not in _codes(items)


def test_falling_muscle_below_maintenance_eases_the_deficit() -> None:
    items = recommend(
        goal="cut",
        sex="female",
        intake=IntakeSnapshot(
            calories=Decimal("2000"),
            protein_g=Decimal("150"),
            fat_g=Decimal("70"),
            carbs_g=Decimal("180"),
        ),
        scans=[
            _scan(0, weight="80", smm="40", bfm="12"),
            _scan(10, weight="79.7", smm="39.8", bfm="12"),
            _scan(21, weight="79.4", smm="39.5", bfm="11.9"),
        ],
    )
    trend = _by_code(items, "trend_ease_deficit")
    assert "200" in trend.text
    maintenance = next(row for row in trend.basis if row.label.startswith("Оценка"))
    # 2000 - (-0.6 * 7000 / 21) = 2200
    assert maintenance.value == "2200"


def test_too_few_scans_skip_the_trend_but_keep_protein() -> None:
    items = recommend(
        goal=GOAL,
        sex="male",
        intake=INTAKE,
        scans=[_scan(0, weight="80"), _scan(10, weight="80")],
    )
    assert "trend_keep" not in _codes(items)
    assert "trend_surplus" not in _codes(items)
    assert "trend_reduce" not in _codes(items)
    note = _by_code(items, "insufficient_scans")
    assert "Данных мало" in note.text
    protein = _by_code(items, "low_protein")
    assert "144" in protein.text
    assert protein.basis[0].value == "1.3"


def test_noise_under_300_grams_counts_as_stable() -> None:
    stalled = recommend(
        goal=GOAL,
        sex=None,
        intake=INTAKE,
        scans=[
            _scan(0),
            _scan(14, weight="80.1"),
            _scan(28, weight="80.2", smm="40.2", bfm="12.2"),
        ],
    )
    assert "trend_surplus" in _codes(stalled)

    moved = recommend(
        goal=GOAL,
        sex=None,
        intake=INTAKE,
        scans=[_scan(0), _scan(14, smm="40.2"), _scan(28, smm="40.3", bfm="12", weight="80")],
    )
    assert "trend_keep" in _codes(moved)
    assert "trend_surplus" not in _codes(moved)


def test_protein_at_the_floor_is_not_a_recommendation() -> None:
    items = recommend(
        goal=GOAL,
        sex="male",
        intake=IntakeSnapshot(
            calories=Decimal("2500"),
            protein_g=Decimal("128"),
            fat_g=Decimal("80"),
            carbs_g=Decimal("280"),
        ),
        scans=[_scan(0), _scan(14), _scan(28)],
    )
    assert "low_protein" not in _codes(items)


def test_low_fat_by_grams_or_by_calorie_share() -> None:
    by_grams = recommend(
        goal=GOAL,
        sex="male",
        intake=IntakeSnapshot(
            calories=Decimal("1800"),
            protein_g=Decimal("140"),
            fat_g=Decimal("50"),
            carbs_g=Decimal("200"),
        ),
        scans=[_scan(0)],
    )
    assert "low_fat" in _codes(by_grams)

    by_share = recommend(
        goal=GOAL,
        sex="male",
        intake=IntakeSnapshot(
            calories=Decimal("4000"),
            protein_g=Decimal("160"),
            fat_g=Decimal("80"),
            carbs_g=Decimal("500"),
        ),
        scans=[_scan(0)],
    )
    assert "low_fat" in _codes(by_share)
    assert "углевод" in _by_code(by_share, "low_fat").text


def test_three_guards_and_no_further_cut() -> None:
    items = recommend(
        goal="cut",
        sex="male",
        intake=IntakeSnapshot(
            calories=Decimal("1400"),
            protein_g=Decimal("140"),
            fat_g=Decimal("50"),
            carbs_g=Decimal("100"),
        ),
        scans=[
            _scan(0, weight="80", smm="40", bfm="10", pbf="12", bmr=1600),
            _scan(10, weight="78.8", smm="39.6", bfm="10.2", pbf="11", bmr=1600),
            _scan(21, weight="77", smm="39.2", bfm="11.2", pbf="9", bmr=1600),
        ],
    )
    codes = _codes(items)
    assert "guard_low_calories" in codes
    assert "guard_fast_loss" in codes
    assert "guard_low_body_fat" in codes
    assert "trend_reduce" not in codes
    for code in ("guard_low_calories", "guard_fast_loss", "guard_low_body_fat"):
        assert "врач" in _by_code(items, code).text


def test_female_floor_is_lower_and_unknown_sex_uses_the_male_floor() -> None:
    scans = [_scan(0, bmr=1100, pbf="20")]
    intake = IntakeSnapshot(
        calories=Decimal("1300"),
        protein_g=Decimal("140"),
        fat_g=Decimal("50"),
        carbs_g=Decimal("80"),
    )
    female = recommend(goal=GOAL, sex="female", intake=intake, scans=scans)
    unknown = recommend(goal=None, sex=None, intake=intake, scans=scans)
    assert "guard_low_calories" not in _codes(female)
    assert "guard_low_calories" in _codes(unknown)
    assert "low_protein" not in _codes(unknown)


def test_missing_intake_still_describes_the_body_trend() -> None:
    items = recommend(
        goal=GOAL,
        sex="male",
        intake=None,
        scans=[
            _scan(0, smm="40", bfm="12"),
            _scan(14, smm="40.3", bfm="12"),
            _scan(28, smm="40.6", bfm="11.8"),
        ],
    )
    assert _codes(items)[0] == "trend_keep" or "no_intake" in _codes(items)
    assert "no_intake" in _codes(items)
    assert "low_protein" not in _codes(items)
    assert "trend_keep" in _codes(items)
