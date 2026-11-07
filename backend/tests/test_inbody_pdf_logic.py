from datetime import date, time
from decimal import Decimal

import pytest
from app.services.inbody_pdf import InbodyPdfError, extract_pdf_text, parse_inbody_text

ENGLISH = """
InBody570
Test Date / Time 2026.11.07. 09:15
Body Composition Analysis
Total Body Water (L) 48.5 ( 31.2 ~ 38.1 )
Protein (kg) 13.2
Body Fat Mass (kg) 16.4 ( 8.0 ~ 16.0 )
Weight (kg) 84.7 ( 55.0 ~ 74.2 )
Skeletal Muscle Mass (kg) 38.2 ( 26.0 ~ 31.8 )
Obesity Analysis
BMI (kg/m2) 27.6
PBF (%) 19.4
Ideal Weight (kg) 70.0
Visceral Fat Level 7
Basal Metabolic Rate 1750 kcal
"""

RUSSIAN = """
Дата тестирования 07.11.2026 09:15
Общее количество воды (L) 48,5
Скелетная мышечная масса (kg) 38,2
Жировая масса (kg) 16,4
Вес (kg) 84,7
Процент жира (%) 19,4
Уровень висцерального жира 7
Основной обмен веществ (kcal) 1750
"""


def test_english_sheet_uses_measured_values_not_the_range_or_ideal_weight() -> None:
    sheet = parse_inbody_text(ENGLISH)

    assert sheet.measured_on == date(2026, 11, 7)
    assert sheet.measured_time == time(9, 15)
    assert sheet.weight_kg == Decimal("84.7")
    assert sheet.smm_kg == Decimal("38.2")
    assert sheet.bfm_kg == Decimal("16.4")
    assert sheet.pbf_percent == Decimal("19.4")
    assert sheet.tbw_l == Decimal("48.5")
    assert sheet.visceral_fat_level == 7
    assert sheet.bmr_kcal == 1750
    assert sheet.missing() == ()


def test_russian_sheet_accepts_a_comma_decimal() -> None:
    sheet = parse_inbody_text(RUSSIAN)

    assert sheet.measured_on == date(2026, 11, 7)
    assert sheet.measured_time == time(9, 15)
    assert sheet.weight_kg == Decimal("84.7")
    assert sheet.pbf_percent == Decimal("19.4")
    assert sheet.missing() == ()


APP_SHEET = """
Имя Алекс Пол М Возраст 30 Рост 190 см Дата 26.10.26
Вес Норма
84.7 кг
Мышцы Выше нормы
43 кг
Жир Норма
11.7 %
История состава тела 26.10.26
Вес , кг 84,7
Мышцы , кг 43
Жир , % 11,7
Вес 84.7 кг
< 67.5 67.5–91.3 > 91.3
Мышцы Выше нормы 43 кг
Жир 11.7 %
< 10 10–20 > 20
Вода Выше нормы 54.8 л
< 44.6 44.6–54.6 > 54.6
Безжировая масса Выше нормы 74.8 кг
Висцеральный жир Ниже нормы 3
< 7 7–10 > 10
До идеального веса
Вес 0 кг Жир 0 кг Мышцы 0 кг
Обмен веществ 1985 ккал
Суточная норма калорий 3010 ккал
Идеальный вес 84.7 кг
Содержание мышц 43 кг
Содержание Жира 9.9 кг
"""


def test_app_result_sheet_reads_short_labels_and_a_two_digit_year() -> None:
    sheet = parse_inbody_text(APP_SHEET)

    assert sheet.measured_on == date(2026, 10, 26)
    assert sheet.weight_kg == Decimal("84.7")
    assert sheet.smm_kg == Decimal("43.0")
    assert sheet.bfm_kg == Decimal("9.9")
    assert sheet.pbf_percent == Decimal("11.7")
    assert sheet.tbw_l == Decimal("54.8")
    assert sheet.visceral_fat_level == 3
    assert sheet.bmr_kcal == 1985
    assert sheet.missing() == ()


def test_clock_on_the_sheet_is_kept_as_the_measurement_time() -> None:
    sheet = parse_inbody_text("Test Date / Time 2026-03-01 14:05 Weight (kg) 80.0")

    assert sheet.measured_time == time(14, 5)
    assert "smm_kg" in sheet.missing()


def test_unrelated_text_has_no_metrics() -> None:
    sheet = parse_inbody_text("Это обычная заметка без замеров тела.")

    assert sheet.weight_kg is None
    assert sheet.measured_on is None
    assert "weight_kg" in sheet.missing()


def test_extract_rejects_a_file_that_is_not_a_pdf() -> None:
    with pytest.raises(InbodyPdfError, match="Это не PDF"):
        extract_pdf_text(b"not a pdf")
