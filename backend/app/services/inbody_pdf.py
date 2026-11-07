"""Текст листа InBody → цифры замера. PDF только отдаёт текст, правила — здесь."""

import re
from dataclasses import dataclass
from datetime import date, time
from decimal import ROUND_HALF_UP, Decimal
from io import BytesIO

from pypdf import PdfReader
from pypdf.errors import PdfReadError

_TENTH = Decimal("0.1")
_MAX_PAGES = 3
_SKIP_BEFORE = (
    "ideal",
    "идеальн",
    "target",
    "нормальн",
    "стандарт",
    "control",
    "контрол",
    "процент",
    "percent",
    "суточн",
    "висцеральн",
    "без",
)
# Между подписью и цифрой на листе приложения InBody стоит оценка: «Выше нормы».
_GAP = (
    r"(?:"
    r"\s*\([^)]{0,40}\)"
    r"|\s*,?\s*(?:кг|kg|%|л|l|ккал|kcal)"
    r"|\s+(?:ниже|выше)\s+норм\w*"
    r"|\s+норм\w*"
    r"|\s+в\s+организме"
    r")*"
)

_DATE_LABEL = re.compile(
    r"(?:test\s*date(?:\s*/\s*time)?|measurement\s+date|дата(?:\s+тестирования)?)",
    re.IGNORECASE,
)
_DATE = re.compile(
    r"(?P<y>\d{4})[./-](?P<m>\d{1,2})[./-](?P<d>\d{1,2})"
    r"|(?P<d2>\d{1,2})[.](?P<m2>\d{1,2})[.](?P<y2>\d{4})"
    r"|(?P<d3>\d{1,2})[.](?P<m3>\d{1,2})[.](?P<y3>\d{2})(?!\d)"
)
_TIME = re.compile(r"(?<!\d)(\d{1,2}):(\d{2})(?!\d)")


class InbodyPdfError(Exception):
    """Лист нельзя прочитать. Текст исключения показывается пользователю."""


@dataclass(frozen=True)
class ParsedSheet:
    measured_on: date | None = None
    measured_time: time | None = None
    weight_kg: Decimal | None = None
    smm_kg: Decimal | None = None
    bfm_kg: Decimal | None = None
    pbf_percent: Decimal | None = None
    tbw_l: Decimal | None = None
    visceral_fat_level: int | None = None
    bmr_kcal: int | None = None

    def missing(self) -> tuple[str, ...]:
        names = (
            "measured_on",
            "weight_kg",
            "smm_kg",
            "bfm_kg",
            "pbf_percent",
            "tbw_l",
            "visceral_fat_level",
            "bmr_kcal",
        )
        return tuple(name for name in names if getattr(self, name) is None)


def parse_inbody_pdf(raw: bytes) -> ParsedSheet:
    """Достаёт текст из PDF и разбирает лист. Пустой или чужой файл — InbodyPdfError."""
    sheet = parse_inbody_text(extract_pdf_text(raw))
    if sheet.weight_kg is None and sheet.pbf_percent is None and sheet.smm_kg is None:
        raise InbodyPdfError("Не удалось найти цифры InBody. Введите их вручную.")
    return sheet


def extract_pdf_text(raw: bytes) -> str:
    if not raw.startswith(b"%PDF"):
        raise InbodyPdfError("Это не PDF")
    try:
        reader = PdfReader(BytesIO(raw))
        if reader.is_encrypted:
            raise InbodyPdfError("PDF закрыт паролем")
        parts = [(page.extract_text() or "") for page in reader.pages[:_MAX_PAGES]]
    except InbodyPdfError:
        raise
    except (PdfReadError, ValueError) as exc:
        raise InbodyPdfError("Не удалось прочитать PDF") from exc
    text = "\n".join(parts).strip()
    if not text:
        raise InbodyPdfError("В PDF нет текста. Скан без распознавания прочитать нельзя.")
    return text


def parse_inbody_text(text: str) -> ParsedSheet:
    flat = _flat(text)
    measured_on, measured_time = _when(flat)
    weight = _decimal(flat, _WEIGHT, low=20, high=400)
    smm = _decimal(flat, _SMM, low=1, high=200)
    bfm = _decimal(flat, _BFM, low=0, high=300)
    pbf = _decimal(flat, _PBF, low=Decimal("0.1"), high=80)
    tbw = _decimal(flat, _TBW, low=1, high=200)
    visceral = _integer(flat, _VISCERAL, low=1, high=30)
    bmr = _integer(flat, _BMR, low=500, high=6000)
    return ParsedSheet(
        measured_on=measured_on,
        measured_time=measured_time,
        weight_kg=weight,
        smm_kg=smm,
        bfm_kg=bfm,
        pbf_percent=pbf,
        tbw_l=tbw,
        visceral_fat_level=visceral,
        bmr_kcal=bmr,
    )


def _flat(text: str) -> str:
    text = text.replace("\u00a0", " ").replace("\u202f", " ")
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\s*\n\s*", " ", text)


def _decimal(
    text: str, labels: tuple[str, ...], *, low: Decimal | int, high: Decimal | int
) -> Decimal | None:
    for raw in _after_label(text, labels):
        value = Decimal(raw.replace(",", ".")).quantize(_TENTH, rounding=ROUND_HALF_UP)
        if Decimal(low) <= value <= Decimal(high):
            return value
    return None


def _integer(text: str, labels: tuple[str, ...], *, low: int, high: int) -> int | None:
    for raw in _after_label(text, labels):
        normalized = raw.replace(",", ".")
        if "." in normalized and Decimal(normalized) != Decimal(normalized).to_integral_value():
            continue
        value = int(Decimal(normalized))
        if low <= value <= high:
            return value
    return None


def _after_label(text: str, labels: tuple[str, ...]) -> list[str]:
    number = re.compile(rf"{_GAP}\s*[:\-]?\s*(\d{{1,4}}(?:[.,]\d{{1,2}})?)", re.IGNORECASE)
    found_values: list[str] = []
    for label in labels:
        pattern = re.compile(label, re.IGNORECASE)
        for found in pattern.finditer(text):
            before = text[max(0, found.start() - 24) : found.start()].lower()
            if re.search(rf"(?:{'|'.join(_SKIP_BEFORE)})\w*\s*$", before):
                continue
            tail = number.match(text[found.end() : found.end() + 64])
            if tail is not None:
                found_values.append(tail.group(1))
    return found_values


def _when(text: str) -> tuple[date | None, time | None]:
    label = _DATE_LABEL.search(text)
    start = label.end() if label else 0
    found = _DATE.search(text, start) or _DATE.search(text)
    if found is None:
        return None, None
    measured = _as_date(found)
    if measured is None:
        return None, None
    clock = _TIME.search(text, found.end(), found.end() + 16)
    if clock is None:
        return measured, None
    hour = int(clock.group(1))
    minute = int(clock.group(2))
    if hour > 23 or minute > 59:
        return measured, None
    return measured, time(hour, minute)


def _as_date(found: re.Match[str]) -> date | None:
    if found.group("y"):
        year, month, day = int(found.group("y")), int(found.group("m")), int(found.group("d"))
    elif found.group("y2"):
        year, month, day = int(found.group("y2")), int(found.group("m2")), int(found.group("d2"))
    else:
        year = int(found.group("y3"))
        year += 2000 if year < 70 else 1900
        month, day = int(found.group("m3")), int(found.group("d3"))
    try:
        return date(year, month, day)
    except ValueError:
        return None


# Более длинные подписи раньше коротких: «жировая масса» не должна съесть «процент жира».
_WEIGHT = (
    r"вес\s*(?:\(кг\)|\(kg\))?",
    r"weight\s*(?:\(kg\)|\(кг\))?",
)
_SMM = (
    r"скелетн\w*[\s-]+мышечн\w*\s+масс\w*(?:\s*\((?:кг|kg)\))?",
    r"skeletal\s+muscle\s+mass(?:\s*\(kg\))?",
    r"\bсмм\b(?:\s*\((?:кг|kg)\))?",
    r"\bsmm\b(?:\s*\(kg\))?",
    r"\bмышц\w*\b",
)
_BFM = (
    r"жировая\s+масс\w*(?:\s*\((?:кг|kg)\))?",
    r"содержание\s+жира(?:\s*\((?:кг|kg)\))?",
    r"масс\w*\s+жира(?:\s*\((?:кг|kg)\))?",
    r"body\s+fat\s+mass(?:\s*\(kg\))?",
    r"\bbfm\b(?:\s*\(kg\))?",
)
_PBF = (
    r"процент\s+(?:содержания\s+)?жира(?:\s*\(%\))?",
    r"percent\s+body\s+fat(?:\s*\(%\))?",
    r"\bpbf\b(?:\s*\(%\))?",
    r"\bжир\b",
)
_TBW = (
    r"общее\s+количество\s+воды(?:\s+в\s+организме)?(?:\s*\([lл]\))?",
    r"общая\s+вода(?:\s+организма)?(?:\s*\([lл]\))?",
    r"total\s+body\s+water(?:\s*\([lл]\))?",
    r"\btbw\b(?:\s*\([lл]\))?",
    r"\bвода\b",
)
_VISCERAL = (
    r"уровень\s+висцерального\s+жира",
    r"висцеральный\s+жир(?:\s*\(уровень\))?",
    r"visceral\s+fat\s+level",
)
_BMR = (
    r"основной\s+обмен(?:\s+веществ)?(?:\s*\((?:ккал|kcal)\))?",
    r"базальн\w*\s+метаболизм(?:\s*\((?:ккал|kcal)\))?",
    r"basal\s+metabolic\s+rate(?:\s*\((?:kcal|ккал)\))?",
    r"\bbmr\b(?:\s*\((?:kcal|ккал)\))?",
    r"обмен\s+веществ",
)
