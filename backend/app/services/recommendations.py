"""Правила рекомендаций spec.md 4.10. Функция ничего не пишет в базу.

Калории на входе — текущий сохранённый уровень, не среднее за 2–3 недели.
Повторный шаг не хранится: те же замеры снова дают тот же один шаг в 200 ккал.
"""

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.inbody import list_scans
from app.services.nutrition import PROTEIN_G_PER_KG, get_intake, present_intake
from app.services.profile import get_profile_or_default

NOISE_KG = Decimal("0.3")
MIN_TREND_SCANS = 3
MIN_SPAN_DAYS = 14
MAX_SPAN_DAYS = 28
STEP_KCAL = 200
MAX_STEP_KCAL = 300
KCAL_PER_KG = Decimal(7000)
PROTEIN_FLOOR_G_PER_KG = Decimal("1.6")
FAT_FLOOR_G_PER_KG = Decimal("0.8")
FAT_CALORIE_SHARE = Decimal("0.20")
WEIGHT_GAIN_PER_WEEK = Decimal("0.005")
WEIGHT_LOSS_PER_WEEK = Decimal("0.01")
MALE_CALORIE_FLOOR = 1500
FEMALE_CALORIE_FLOOR = 1200
MALE_PBF_GUARD = Decimal("10")
FEMALE_PBF_GUARD = Decimal("18")

INTAKE_SOURCE = "текущий уровень, не среднее за 2–3 недели"
DISCLAIMER = "Приложение не заменяет консультацию врача или диетолога."

_TENTH = Decimal("0.1")
_KCAL = Decimal("1")


@dataclass(frozen=True)
class BasisValue:
    label: str
    value: str


@dataclass(frozen=True)
class Recommendation:
    code: str
    text: str
    basis: tuple[BasisValue, ...]


@dataclass(frozen=True)
class IntakeSnapshot:
    calories: Decimal
    protein_g: Decimal
    fat_g: Decimal
    carbs_g: Decimal


@dataclass(frozen=True)
class ScanSnapshot:
    measured_on: date
    weight_kg: Decimal
    smm_kg: Decimal
    bfm_kg: Decimal
    pbf_percent: Decimal
    bmr_kcal: int


def recommend(
    *,
    goal: str | None,
    sex: str | None,
    intake: IntakeSnapshot | None,
    scans: list[ScanSnapshot],
) -> list[Recommendation]:
    """Список выводов. Пустой список значит, что по этим данным советов нет."""
    ordered = sorted(scans, key=lambda scan: scan.measured_on)
    items: list[Recommendation] = []
    window, span = _window(ordered)
    trend_ready = len(window) >= MIN_TREND_SCANS and MIN_SPAN_DAYS <= span <= MAX_SPAN_DAYS
    guards = _guards(sex=sex, intake=intake, window=window, span=span)
    items.extend(guards)

    if intake is None:
        items.append(
            Recommendation(
                code="no_intake",
                text=(
                    "Текущие белки, жиры и углеводы не сохранены, "
                    "поэтому советы по ним не считаются."
                ),
                basis=(),
            )
        )
    elif ordered:
        latest = ordered[-1]
        protein = _low_protein(goal, intake, latest)
        if protein is not None:
            items.append(protein)
        fat = _low_fat(intake, latest)
        if fat is not None:
            items.append(fat)

    if trend_ready:
        trend = _trend(
            goal=goal,
            intake=intake,
            window=window,
            span=span,
            block_cut=bool(guards),
        )
        if trend is not None:
            items.append(trend)
    else:
        items.append(_insufficient(window, span))
    return items


async def collect_recommendations(db: AsyncSession, user_id: uuid.UUID) -> list[Recommendation]:
    """Собирает профиль, текущее БЖУ и свои замеры. Чужие строки в выборку не попадают."""
    profile = await get_profile_or_default(db, user_id)
    row = await get_intake(db, user_id)
    intake = None
    if row is not None:
        view = present_intake(row)
        assert view.calories is not None and view.protein_g is not None
        assert view.fat_g is not None and view.carbs_g is not None
        intake = IntakeSnapshot(
            calories=view.calories,
            protein_g=view.protein_g,
            fat_g=view.fat_g,
            carbs_g=view.carbs_g,
        )
    scans = [
        ScanSnapshot(
            measured_on=scan.measured_on,
            weight_kg=scan.weight_kg,
            smm_kg=scan.smm_kg,
            bfm_kg=scan.bfm_kg,
            pbf_percent=scan.pbf_percent,
            bmr_kcal=scan.bmr_kcal,
        )
        for scan in await list_scans(db, user_id)
    ]
    return recommend(goal=profile.goal, sex=profile.sex, intake=intake, scans=scans)


def _window(scans: list[ScanSnapshot]) -> tuple[list[ScanSnapshot], int]:
    if not scans:
        return [], 0
    latest = scans[-1].measured_on
    window = [scan for scan in scans if (latest - scan.measured_on).days <= MAX_SPAN_DAYS]
    span = (window[-1].measured_on - window[0].measured_on).days
    return window, span


def _direction(delta: Decimal) -> str:
    if abs(delta) < NOISE_KG:
        return "stable"
    if delta > 0:
        return "up"
    return "down"


def _kcal(value: Decimal) -> str:
    return str(int(value.quantize(_KCAL, rounding=ROUND_HALF_UP)))


def _num(value: Decimal) -> str:
    return str(value.quantize(_TENTH, rounding=ROUND_HALF_UP))


def _intake_basis() -> BasisValue:
    return BasisValue("Откуда калории", INTAKE_SOURCE)


def _maintenance(calories: Decimal, weight_delta: Decimal, days: int) -> Decimal:
    return calories - (weight_delta * KCAL_PER_KG / Decimal(days))


def _weekly(start_weight: Decimal, weight_delta: Decimal, days: int) -> Decimal:
    if start_weight <= 0 or days <= 0:
        return Decimal(0)
    return (weight_delta / start_weight) / (Decimal(days) / Decimal(7))


def _calorie_floor(sex: str | None) -> int:
    if sex == "female":
        return FEMALE_CALORIE_FLOOR
    return MALE_CALORIE_FLOOR


def _pbf_guard_limit(sex: str | None) -> Decimal:
    if sex == "female":
        return FEMALE_PBF_GUARD
    return MALE_PBF_GUARD


def _guards(
    *,
    sex: str | None,
    intake: IntakeSnapshot | None,
    window: list[ScanSnapshot],
    span: int,
) -> list[Recommendation]:
    items: list[Recommendation] = []
    latest = window[-1] if window else None
    if intake is not None and latest is not None:
        floor = _calorie_floor(sex)
        below_floor = intake.calories < floor
        below_bmr = intake.calories < latest.bmr_kcal
        if below_floor or below_bmr:
            items.append(
                Recommendation(
                    code="guard_low_calories",
                    text=(
                        "Калории выглядят очень низкими. Рассмотрите обращение к врачу "
                        "или диетологу, прежде чем снижать их дальше."
                    ),
                    basis=(
                        BasisValue("Калории, ккал", _kcal(intake.calories)),
                        BasisValue("Порог, ккал", str(floor)),
                        BasisValue("Обмен веществ замера, ккал", str(latest.bmr_kcal)),
                        _intake_basis(),
                    ),
                )
            )
        if below_bmr and latest.pbf_percent < _pbf_guard_limit(sex):
            items.append(
                Recommendation(
                    code="guard_low_body_fat",
                    text=(
                        "Калории ниже обмена веществ при невысоком проценте жира. "
                        "Рассмотрите обращение к врачу или диетологу."
                    ),
                    basis=(
                        BasisValue("Калории, ккал", _kcal(intake.calories)),
                        BasisValue("Обмен веществ замера, ккал", str(latest.bmr_kcal)),
                        BasisValue("Жир, %", _num(latest.pbf_percent)),
                        _intake_basis(),
                    ),
                )
            )
    if len(window) >= 2 and span >= MIN_SPAN_DAYS:
        start = window[0]
        end = window[-1]
        weight_delta = end.weight_kg - start.weight_kg
        if _weekly(start.weight_kg, weight_delta, span) < -WEIGHT_LOSS_PER_WEEK:
            items.append(
                Recommendation(
                    code="guard_fast_loss",
                    text=(
                        "Вес снижается быстрее примерно 1% в неделю. Обратите внимание "
                        "на самочувствие и рассмотрите консультацию врача или диетолога."
                    ),
                    basis=(
                        BasisValue("Изменение веса, кг", _num(weight_delta)),
                        BasisValue("Дней", str(span)),
                        BasisValue("Вес в начале окна, кг", _num(start.weight_kg)),
                    ),
                )
            )
    return items


def _low_protein(
    goal: str | None, intake: IntakeSnapshot, latest: ScanSnapshot
) -> Recommendation | None:
    if latest.weight_kg <= 0:
        return None
    per_kg = intake.protein_g / latest.weight_kg
    if per_kg >= PROTEIN_FLOOR_G_PER_KG:
        return None
    if goal not in PROTEIN_G_PER_KG:
        return Recommendation(
            code="low_protein",
            text=(
                "Белок ниже 1,6 г на кг веса. Это первая правка, до калорий. "
                "Выберите цель в настройках, чтобы назвать ориентир в граммах."
            ),
            basis=(
                BasisValue("Белок, г/кг", _num(per_kg)),
                BasisValue("Последний вес, кг", _num(latest.weight_kg)),
                BasisValue("Порог, г/кг", _num(PROTEIN_FLOOR_G_PER_KG)),
            ),
        )
    rate = PROTEIN_G_PER_KG[goal]
    target = (rate * latest.weight_kg).quantize(_TENTH, rounding=ROUND_HALF_UP)
    return Recommendation(
        code="low_protein",
        text=(
            f"Белок ниже 1,6 г на кг веса. Рассмотрите поднять его примерно до {target} г "
            f"({rate} г/кг). Это первая правка, до изменения калорий."
        ),
        basis=(
            BasisValue("Белок, г/кг", _num(per_kg)),
            BasisValue("Последний вес, кг", _num(latest.weight_kg)),
            BasisValue("Ориентир, г/кг", _num(rate)),
            BasisValue("Ориентир, г", _num(target)),
        ),
    )


def _low_fat(intake: IntakeSnapshot, latest: ScanSnapshot) -> Recommendation | None:
    if latest.weight_kg <= 0:
        return None
    per_kg = intake.fat_g / latest.weight_kg
    share = Decimal(0) if intake.calories <= 0 else intake.fat_g * 9 / intake.calories
    if per_kg >= FAT_FLOOR_G_PER_KG and share >= FAT_CALORIE_SHARE:
        return None
    return Recommendation(
        code="low_fat",
        text=(
            "Жиры ниже 0,8 г на кг или 20% калорий. Рассмотрите поднять жиры. "
            "Если калории при этом вырастут, добирайте прибавку углеводами."
        ),
        basis=(
            BasisValue("Жиры, г/кг", _num(per_kg)),
            BasisValue("Доля жиров, %", _num(share * 100)),
            BasisValue("Последний вес, кг", _num(latest.weight_kg)),
            _intake_basis(),
        ),
    )


def _insufficient(window: list[ScanSnapshot], span: int) -> Recommendation:
    return Recommendation(
        code="insufficient_scans",
        text=(
            "Данных мало для вывода по тренду: нужно не меньше трёх замеров, "
            "а промежуток между первым и последним — от 14 до 28 дней. "
            "Ориентируйтесь на несколько замеров, а не на одну цифру."
        ),
        basis=(
            BasisValue("Замеров в окне", str(len(window))),
            BasisValue("Дней в окне", str(span)),
        ),
    )


def _trend(
    *,
    goal: str | None,
    intake: IntakeSnapshot | None,
    window: list[ScanSnapshot],
    span: int,
    block_cut: bool,
) -> Recommendation | None:
    start = window[0]
    end = window[-1]
    smm_delta = end.smm_kg - start.smm_kg
    bfm_delta = end.bfm_kg - start.bfm_kg
    weight_delta = end.weight_kg - start.weight_kg
    smm = _direction(smm_delta)
    bfm = _direction(bfm_delta)
    weight = _direction(weight_delta)
    weekly = _weekly(start.weight_kg, weight_delta, span)
    maintenance = None if intake is None else _maintenance(intake.calories, weight_delta, span)
    shared = (
        BasisValue("Изменение мышц, кг", _num(smm_delta)),
        BasisValue("Изменение жира, кг", _num(bfm_delta)),
        BasisValue("Изменение веса, кг", _num(weight_delta)),
        BasisValue("Дней в окне", str(span)),
        BasisValue("Замеров в окне", str(len(window))),
    )
    intake_note = (_intake_basis(),) if intake is not None else ()

    if (
        smm == "down"
        and intake is not None
        and maintenance is not None
        and intake.calories < maintenance
    ):
        assert STEP_KCAL <= MAX_STEP_KCAL
        return Recommendation(
            code="trend_ease_deficit",
            text=(
                "Мышцы снижаются, а текущие калории ниже оценки поддержания. "
                f"Рассмотрите уменьшить дефицит примерно на {STEP_KCAL} ккал и проверить белок."
            ),
            basis=(
                *shared,
                BasisValue("Калории, ккал", _kcal(intake.calories)),
                BasisValue("Оценка поддержания, ккал", _kcal(maintenance)),
                BasisValue("Шаг, ккал", str(STEP_KCAL)),
                *intake_note,
            ),
        )

    fat_faster = bfm == "up" and bfm_delta > smm_delta
    weight_fast = weekly > WEIGHT_GAIN_PER_WEEK
    if (fat_faster or weight_fast) and not block_cut:
        assert STEP_KCAL <= MAX_STEP_KCAL
        return Recommendation(
            code="trend_reduce",
            text=(
                "Жир растёт быстрее мышц или вес растёт быстрее примерно 0,5% в неделю. "
                f"Рассмотрите снизить калории примерно на {STEP_KCAL} ккал."
            ),
            basis=(*shared, BasisValue("Шаг, ккал", str(STEP_KCAL)), *intake_note),
        )

    if smm == "up" and bfm in {"stable", "down"}:
        return Recommendation(
            code="trend_keep",
            text="Мышцы растут, а жир стоит или снижается. Менять калории сейчас не нужно.",
            basis=(*shared, *intake_note),
        )

    if smm == "stable" and bfm == "stable" and weight == "stable" and goal == "muscle_gain":
        assert STEP_KCAL <= MAX_STEP_KCAL
        return Recommendation(
            code="trend_surplus",
            text=(
                "Мышцы, жир и вес почти не меняются при цели набора. "
                f"Рассмотрите прибавку около {STEP_KCAL} ккал, в основном за счёт углеводов."
            ),
            basis=(*shared, BasisValue("Шаг, ккал", str(STEP_KCAL)), *intake_note),
        )
    return None
