from decimal import Decimal

from app.services.nutrition import (
    FAT_G_PER_KG,
    PROTEIN_G_PER_KG,
    MacroTarget,
    macro_calories,
    target_macros,
)

SCAN = {"weight_kg": Decimal("80"), "body_fat_percent": Decimal("20")}


def test_calories_follow_the_macro_coefficients() -> None:
    calories = macro_calories(
        protein_g=Decimal("100"),
        carbs_g=Decimal("200"),
        fat_g=Decimal("50"),
    )
    assert calories == Decimal("1650.0")
    tenths = macro_calories(
        protein_g=Decimal("10.1"),
        carbs_g=Decimal("10.3"),
        fat_g=Decimal("10.2"),
    )
    assert tenths == Decimal("173.4")


def test_target_for_each_goal_on_the_same_scan() -> None:
    maintenance = target_macros(goal="maintenance", **SCAN)
    muscle = target_macros(goal="muscle_gain", **SCAN)
    cut = target_macros(goal="cut", **SCAN)
    recomp = target_macros(goal="recomposition", **SCAN)

    assert maintenance == MacroTarget(
        protein_g=Decimal("128.0"),
        fat_g=Decimal("80.0"),
        carbs_g=Decimal("349.3"),
        calories=2629,
    )
    assert muscle == MacroTarget(
        protein_g=Decimal("144.0"),
        fat_g=Decimal("64.0"),
        carbs_g=Decimal("431.8"),
        calories=2879,
    )
    assert cut == MacroTarget(
        protein_g=Decimal("176.0"),
        fat_g=Decimal("64.0"),
        carbs_g=Decimal("274.8"),
        calories=2379,
    )
    assert recomp == MacroTarget(
        protein_g=Decimal("160.0"),
        fat_g=Decimal("72.0"),
        carbs_g=Decimal("335.3"),
        calories=2629,
    )
    assert muscle.calories == maintenance.calories + 250
    assert cut.calories == maintenance.calories - 250
    assert recomp.calories == maintenance.calories
    assert recomp.protein_g != maintenance.protein_g


def test_target_keeps_protein_fat_and_carb_remainder_inside_the_rule() -> None:
    goal = "maintenance"
    result = target_macros(goal=goal, **SCAN)
    assert result.protein_g is not None
    assert result.fat_g is not None
    assert result.carbs_g is not None
    assert result.calories is not None

    weight = SCAN["weight_kg"]
    protein_per_kg = result.protein_g / weight
    assert Decimal("1.6") <= protein_per_kg <= Decimal("2.2")
    assert protein_per_kg == PROTEIN_G_PER_KG[goal]
    assert result.fat_g / weight >= FAT_G_PER_KG[goal]
    assert result.fat_g * 9 >= Decimal(result.calories) * Decimal("0.20")
    spent = result.protein_g * 4 + result.fat_g * 9 + result.carbs_g * 4
    assert abs(spent - Decimal(result.calories)) <= Decimal("0.2")


def test_fat_rises_to_twenty_percent_of_calories() -> None:
    # 0,8 г/кг от 60 кг — 48 г, это меньше 20% калорий набора.
    result = target_macros(
        goal="muscle_gain",
        weight_kg=Decimal("60"),
        body_fat_percent=Decimal("10"),
    )
    assert result == MacroTarget(
        protein_g=Decimal("108.0"),
        fat_g=Decimal("56.8"),
        carbs_g=Decimal("403.0"),
        calories=2555,
    )
    assert result.fat_g is not None
    assert result.fat_g > Decimal("48")


def test_missing_or_unusable_inputs_return_an_empty_target() -> None:
    empty = MacroTarget()
    cases = [
        {"goal": None, "weight_kg": Decimal("80"), "body_fat_percent": Decimal("20")},
        {"goal": "cut", "weight_kg": None, "body_fat_percent": Decimal("20")},
        {"goal": "cut", "weight_kg": Decimal("80"), "body_fat_percent": None},
        {"goal": "bulk", "weight_kg": Decimal("80"), "body_fat_percent": Decimal("20")},
        {"goal": "cut", "weight_kg": Decimal("0"), "body_fat_percent": Decimal("20")},
        {"goal": "cut", "weight_kg": Decimal("-5"), "body_fat_percent": Decimal("20")},
        {"goal": "cut", "weight_kg": Decimal("80"), "body_fat_percent": Decimal("0")},
        {"goal": "cut", "weight_kg": Decimal("80"), "body_fat_percent": Decimal("100")},
        {"goal": "cut", "weight_kg": float("nan"), "body_fat_percent": Decimal("20")},
    ]
    for case in cases:
        result = target_macros(**case)
        assert result == empty, case
        assert result.is_empty()


def test_target_is_empty_when_protein_and_fat_do_not_fit_the_calories() -> None:
    # Высокий вес и доля жира: нижние границы белка и жиров не входят в калории сушки.
    result = target_macros(goal="cut", weight_kg=Decimal("200"), body_fat_percent=Decimal("95"))
    assert result.is_empty()
