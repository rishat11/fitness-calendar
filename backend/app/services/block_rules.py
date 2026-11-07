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
) -> list[Slot]:
    """Все слоты блока: по одному на каждый день расписания в каждой неделе.

    `weeks` и `schedule` — снимки из размещения. Неделя с номером `i` берёт параметры
    `weeks[i]`, день расписания сопоставляется по `day_index`.
    """
    by_day = {item["day_index"]: item for item in schedule}
    slots: list[Slot] = []
    for offset in range(length_weeks * DAYS_IN_WEEK):
        item = by_day.get(offset % DAYS_IN_WEEK)
        if item is None:
            continue
        if item["kind"] == "rest":
            items: list[dict[str, Any]] = []
        else:
            items = apply_week(item["items"], weeks[offset // DAYS_IN_WEEK])
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


def block_end(start: dt.date, length_weeks: int) -> dt.date:
    """Последний день исходной длины блока: старт плюс недели без одного дня."""
    return start + dt.timedelta(days=length_weeks * DAYS_IN_WEEK - 1)
