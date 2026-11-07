from decimal import Decimal

from app.services.inbody import metric_delta


def test_delta_is_absolute_and_relative_unless_the_base_is_zero() -> None:
    weight = metric_delta(Decimal("84.7"), Decimal("85.1"), code="weight_kg", unit="kg")
    assert weight.absolute == Decimal("0.4")
    assert weight.relative_percent == Decimal("0.5")

    fat = metric_delta(Decimal("11.7"), Decimal("12.0"), code="pbf_percent", unit="pp")
    assert fat.absolute == Decimal("0.3")
    assert fat.relative_percent == Decimal("2.6")

    visceral = metric_delta(Decimal(3), Decimal(4), code="visceral_fat_level", unit="level")
    assert visceral.absolute == Decimal("1.0")
    assert visceral.relative_percent == Decimal("33.3")

    empty = metric_delta(Decimal(0), Decimal("1.0"), code="smm_kg", unit="kg")
    assert empty.absolute == Decimal("1.0")
    assert empty.relative_percent is None
