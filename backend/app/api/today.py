import datetime as dt
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, DbSession
from app.schemas.plan import TodayResponse
from app.services.today import today_board
from app.services.transfer import export_reminder_due

router = APIRouter(prefix="/api/today", tags=["today"])


@router.get("", response_model=TodayResponse)
async def get_today(
    user: CurrentUser,
    db: DbSession,
    day: Annotated[dt.date, Query(description="Календарная дата без часового пояса")],
) -> TodayResponse:
    board = await today_board(db, user.id, day)
    return board.model_copy(update={"export_reminder": await export_reminder_due(db, user)})
