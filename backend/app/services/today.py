import datetime as dt
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.log import PerformedWorkout
from app.models.plan import KIND_WORKOUT
from app.schemas.plan import PlanEntryResponse, TodayEntryResponse, TodayLogState, TodayResponse
from app.services.plan import list_entries


async def _log_states(
    db: AsyncSession, user_id: uuid.UUID, planned_ids: list[uuid.UUID]
) -> dict[uuid.UUID, TodayLogState]:
    """Состояние лога только по записям этого пользователя."""
    if not planned_ids:
        return {}
    rows = await db.execute(
        select(PerformedWorkout.planned_id, PerformedWorkout.finished_at).where(
            PerformedWorkout.user_id == user_id,
            PerformedWorkout.planned_id.in_(planned_ids),
        )
    )
    states: dict[uuid.UUID, TodayLogState] = {}
    for planned_id, finished_at in rows.all():
        if planned_id is None:
            continue
        states[planned_id] = "finished" if finished_at is not None else "open"
    return states


async def today_board(db: AsyncSession, user_id: uuid.UUID, day: dt.date) -> TodayResponse:
    """План на календарный день и признак, можно ли тренировку открыть или продолжить."""
    entries = await list_entries(db, user_id, day, day)
    states = await _log_states(
        db, user_id, [entry.id for entry in entries if entry.kind == KIND_WORKOUT]
    )
    payload = [
        TodayEntryResponse(
            **PlanEntryResponse.model_validate(entry).model_dump(),
            log_state=states.get(entry.id, "none"),
        )
        for entry in entries
    ]
    return TodayResponse(date=day, entries=payload)
