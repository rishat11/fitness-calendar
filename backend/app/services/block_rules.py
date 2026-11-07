"""Правила блока без базы: слоты календаря от даты старта и наложение параметров недели.

Слот — это тренировка или отдых, который блок ставит на конкретный день. Слоты не лежат
в базе: дата считается из `start_date`, а номер дня `day_offset` от исходного старта
не меняется, поэтому он служит стабильным ключом даже после сдвига блока.
"""

import datetime as dt
import uuid
from dataclasses import dataclass
from typing import Any

DAYS_IN_WEEK = 7
# Поиск открытой тренировки бесконечного блока: дальше этого горизонта id не ищем.
REPEAT_LOOKUP_DAYS = 366 * 20
# При применении проверяем пересечение с уже стоящим планом на этот срок вперёд.
REPEAT_CONFLICT_DAYS = 366 * 2
# Пространство имён для стабильных id тренировок блока.
_SLOT_NAMESPACE = uuid.UUID("6f1d0c7e-3a52-4f63-9b1e-2c8d5a7e4b10")


@dataclass(frozen=True, slots=True)
class Slot:
    placement_id: uuid.UUID
    # Номер дня от исходного старта блока: 0 — первый день первой недели.
    day_offset: int
    id: uuid.UUID
    date: dt.date
    kind: str
    name: str | None
    items: list[dict[str, Any]]


def slot_id(placement_id: uuid.UUID, day_offset: int) -> uuid.UUID:
    """Id слота детерминирован: тот же день блока всегда получает тот же id."""
    return uuid.uuid5(_SLOT_NAMESPACE, f"{placement_id}:{day_offset}")


def apply_week(items: list[dict[str, Any]], week: dict[str, Any]) -> list[dict[str, Any]]:
    """Накладывает параметры недели на снимок тренировки.

    Диапазон повторов и целевой RIR берутся из недели для каждого подхода. Множитель
    объёма оставляет долю подходов упражнения, но не меньше одного подхода.
    """
    result: list[dict[str, Any]] = []
    for item in items:
        sets = list(item["sets"])
        keep = max(1, int(len(sets) * float(week["volume_multiplier"]) + 0.5))
        new_sets = [
            {
                **set_,
                "rep_min": week["rep_min"],
                "rep_max": week["rep_max"],
                "target_rir": week["target_rir"],
            }
            for set_ in sets[:keep]
        ]
        result.append({**item, "sets": new_sets})
    return result


def build_slots(
    placement_id: uuid.UUID,
    start: dt.date,
    length_weeks: int,
    weeks: list[dict[str, Any]],
    schedule: list[dict[str, Any]],
    cycle_days: int = DAYS_IN_WEEK,
    *,
    repeats: bool = False,
    window: tuple[dt.date, dt.date] | None = None,
) -> list[Slot]:
    """Слоты блока: по одному на каждый день расписания.

    `weeks` и `schedule` — снимки из размещения. День расписания сопоставляется по
    `day_index` внутри цикла. Без `repeats` цикл с номером `i` берёт `weeks[i]` и
    слоты кончаются вместе с блоком. С `repeats` те же циклы идут по кругу, а `window`
    ограничивает даты, которые нужно посчитать.
    """
    if cycle_days < 1 or length_weeks < 1 or not weeks:
        return []
    by_day = {item["day_index"]: item for item in schedule}
    span = length_weeks * cycle_days
    first = 0
    last = span - 1
    if repeats and window is not None:
        first = max(0, (window[0] - start).days)
        last = (window[1] - start).days
    elif window is not None:
        first = max(first, (window[0] - start).days)
        last = min(last, (window[1] - start).days)
    if last < first:
        return []
    slots: list[Slot] = []
    for offset in range(first, last + 1):
        item = by_day.get(offset % cycle_days)
        if item is None:
            continue
        week_index = offset // cycle_days
        if repeats:
            week_index %= len(weeks)
        elif week_index >= len(weeks):
            continue
        if item["kind"] == "rest":
            items: list[dict[str, Any]] = []
        else:
            items = apply_week(item["items"], weeks[week_index])
        slots.append(
            Slot(
                placement_id=placement_id,
                day_offset=offset,
                id=slot_id(placement_id, offset),
                date=start + dt.timedelta(days=offset),
                kind=item["kind"],
                name=item.get("name"),
                items=items,
            )
        )
    return slots


def block_end(start: dt.date, length_weeks: int, cycle_days: int = DAYS_IN_WEEK) -> dt.date:
    """Последний день блока: старт плюс циклы заданной длины без одного дня."""
    return start + dt.timedelta(days=length_weeks * cycle_days - 1)
