"""Замеры InBody: запись и сравнение с предыдущим. Сессию не коммитит."""

import uuid
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.inbody import InbodyScan
from app.schemas.inbody import InbodyScanInput

_TENTH = Decimal("0.1")

# Код, подпись единицы. Для жира и висцерального уровня абсолют — пункты, не килограммы.
_DELTAS: tuple[tuple[str, str], ...] = (
    ("weight_kg", "kg"),
    ("smm_kg", "kg"),
    ("bfm_kg", "kg"),
    ("tbw_l", "l"),
    ("pbf_percent", "pp"),
    ("visceral_fat_level", "level"),
)


@dataclass(frozen=True)
class MetricDelta:
    code: str
    absolute: Decimal
    relative_percent: Decimal | None
    unit: str


def metric_delta(previous: Decimal, current: Decimal, *, code: str, unit: str) -> MetricDelta:
    """Абсолют и относительный процент. При нулевой базе процент не выдумывается."""
    absolute = (current - previous).quantize(_TENTH, rounding=ROUND_HALF_UP)
    if previous == 0:
        return MetricDelta(code=code, absolute=absolute, relative_percent=None, unit=unit)
    relative = ((current - previous) / previous * Decimal(100)).quantize(
        _TENTH, rounding=ROUND_HALF_UP
    )
    return MetricDelta(code=code, absolute=absolute, relative_percent=relative, unit=unit)


def deltas_against(previous: InbodyScan, current: InbodyScan) -> tuple[MetricDelta, ...]:
    result: list[MetricDelta] = []
    for code, unit in _DELTAS:
        result.append(
            metric_delta(
                Decimal(getattr(previous, code)),
                Decimal(getattr(current, code)),
                code=code,
                unit=unit,
            )
        )
    return tuple(result)


def _tenth(value: float) -> Decimal:
    return Decimal(str(value)).quantize(_TENTH, rounding=ROUND_HALF_UP)


def _segments(body: InbodyScanInput) -> dict[str, Any] | None:
    if body.segments is None:
        return None
    return body.segments.model_dump(mode="json")


def _apply(row: InbodyScan, body: InbodyScanInput) -> None:
    row.measured_on = body.measured_on
    row.measured_time = body.measured_time
    row.weight_kg = _tenth(body.weight_kg)
    row.smm_kg = _tenth(body.smm_kg)
    row.bfm_kg = _tenth(body.bfm_kg)
    row.pbf_percent = _tenth(body.pbf_percent)
    row.tbw_l = _tenth(body.tbw_l)
    row.visceral_fat_level = body.visceral_fat_level
    row.bmr_kcal = body.bmr_kcal
    row.segments = _segments(body)


async def list_scans(db: AsyncSession, user_id: uuid.UUID) -> list[InbodyScan]:
    """Замеры только этого пользователя, от раннего к позднему."""
    rows = await db.scalars(
        select(InbodyScan)
        .where(InbodyScan.user_id == user_id)
        .order_by(InbodyScan.measured_on, InbodyScan.measured_time, InbodyScan.id)
    )
    return list(rows)


async def latest_scan(db: AsyncSession, user_id: uuid.UUID) -> InbodyScan | None:
    rows = await list_scans(db, user_id)
    if not rows:
        return None
    return rows[-1]


async def get_scan(db: AsyncSession, user_id: uuid.UUID, scan_id: uuid.UUID) -> InbodyScan | None:
    return await db.scalar(
        select(InbodyScan).where(InbodyScan.user_id == user_id, InbodyScan.id == scan_id)
    )


async def create_scan(db: AsyncSession, user_id: uuid.UUID, body: InbodyScanInput) -> InbodyScan:
    row = InbodyScan(id=uuid.uuid4(), user_id=user_id, measured_on=body.measured_on)
    _apply(row, body)
    db.add(row)
    await db.flush()
    return row


async def replace_scan(row: InbodyScan, body: InbodyScanInput) -> InbodyScan:
    _apply(row, body)
    return row


def attach_comparisons(
    rows: list[InbodyScan],
) -> list[tuple[InbodyScan, tuple[MetricDelta, ...]]]:
    """К каждому замеру — дельты относительно предыдущего по времени."""
    attached: list[tuple[InbodyScan, tuple[MetricDelta, ...]]] = []
    previous: InbodyScan | None = None
    for row in rows:
        attached.append((row, () if previous is None else deltas_against(previous, row)))
        previous = row
    return attached


def comparison_for(
    rows: list[InbodyScan], scan_id: uuid.UUID
) -> tuple[InbodyScan, tuple[MetricDelta, ...]]:
    for row, deltas in attach_comparisons(rows):
        if row.id == scan_id:
            return row, deltas
    raise LookupError(scan_id)
