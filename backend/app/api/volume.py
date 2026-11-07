import datetime as dt
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, DbSession
from app.schemas.volume import VolumeWeekResponse
from app.services.volume import muscle_volume

router = APIRouter(prefix="/api/volume", tags=["volume"])


@router.get("/muscles", response_model=VolumeWeekResponse)
async def read_muscle_volume(
    user: CurrentUser,
    db: DbSession,
    day: Annotated[
        dt.date,
        Query(description="Любая дата нужной недели; неделя считается пн–вс"),
    ],
) -> VolumeWeekResponse:
    return await muscle_volume(db, user.id, day)
