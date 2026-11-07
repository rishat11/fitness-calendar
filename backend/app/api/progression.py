import uuid
from typing import NoReturn

from fastapi import APIRouter, HTTPException, status

from app.api.deps import CurrentUser, DbSession
from app.schemas.progression import (
    ProgressionDecisionResult,
    ProgressionDecisionWrite,
    ProgressionHintResponse,
)
from app.services.progression import ProgressionError, decide, visible_hint

router = APIRouter(prefix="/api/progression", tags=["progression"])


def _fail(exc: ProgressionError) -> NoReturn:
    code = status.HTTP_404_NOT_FOUND if exc.missing else status.HTTP_422_UNPROCESSABLE_ENTITY
    raise HTTPException(status_code=code, detail=str(exc)) from None


@router.get("/{exercise_id}", response_model=ProgressionHintResponse | None)
async def read_hint(
    exercise_id: uuid.UUID, user: CurrentUser, db: DbSession
) -> ProgressionHintResponse | None:
    try:
        hint = await visible_hint(db, user.id, exercise_id)
    except ProgressionError as exc:
        _fail(exc)
    if hint is None:
        return None
    return ProgressionHintResponse(
        exercise_id=exercise_id,
        status=hint.status,
        message=hint.message,
        suggested_weight=hint.suggested_weight,
        weight_unit=hint.weight_unit,  # type: ignore[arg-type]
        last_session_id=hint.last_session_id,
        epley_1rm=hint.epley_1rm,
    )


@router.post("/{exercise_id}/decision", response_model=ProgressionDecisionResult)
async def write_decision(
    exercise_id: uuid.UUID,
    body: ProgressionDecisionWrite,
    user: CurrentUser,
    db: DbSession,
) -> ProgressionDecisionResult:
    try:
        outcome = await decide(
            db, user.id, exercise_id, body.action, performed_id=body.performed_id
        )
    except ProgressionError as exc:
        _fail(exc)
    payload = ProgressionDecisionResult(
        action=outcome.action,  # type: ignore[arg-type]
        performed_id=outcome.performed_id,
        set_id=outcome.set_id,
        weight=outcome.weight,
    )
    await db.commit()
    return payload
