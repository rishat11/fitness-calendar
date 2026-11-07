import uuid
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Response, status

from app.api.deps import CurrentUser, DbSession
from app.schemas.log import (
    ExerciseReplace,
    ItemCreate,
    NoteWrite,
    PerformedStart,
    PerformedWorkoutResponse,
    PreviousSets,
    SetCreate,
    SetLogResponse,
    SetWrite,
)
from app.services.log import (
    LogError,
    add_item,
    add_set,
    delete_set,
    finish,
    previous_sets,
    replace_exercise,
    start_from_plan,
    to_response,
    to_set,
    update_item_note,
    update_note,
    update_set,
)

router = APIRouter(prefix="/api/performed", tags=["performed"])


def _fail(exc: LogError) -> None:
    # «не найден» — нет такой записи у пользователя. Остальное клиент может исправить.
    code = status.HTTP_404_NOT_FOUND if "не найден" in str(exc) else 422
    raise HTTPException(status_code=code, detail=str(exc)) from None


@router.post("", response_model=PerformedWorkoutResponse)
async def start_performed(
    body: PerformedStart, user: CurrentUser, db: DbSession, response: Response
) -> PerformedWorkoutResponse:
    try:
        workout, created = await start_from_plan(db, user.id, body.planned_id)
    except LogError as exc:
        _fail(exc)
    payload = to_response(workout)
    await db.commit()
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    return payload


@router.get("/previous", response_model=PreviousSets | None)
async def exercise_previous(
    user: CurrentUser,
    db: DbSession,
    exercise_id: Annotated[uuid.UUID, Query()],
    exclude_id: Annotated[uuid.UUID | None, Query()] = None,
) -> PreviousSets | None:
    try:
        return await previous_sets(db, user.id, exercise_id, exclude_id=exclude_id)
    except LogError as exc:
        _fail(exc)


@router.patch("/{performed_id}", response_model=PerformedWorkoutResponse)
async def patch_performed_note(
    performed_id: uuid.UUID, body: NoteWrite, user: CurrentUser, db: DbSession
) -> PerformedWorkoutResponse:
    try:
        workout = await update_note(db, user.id, performed_id, body)
    except LogError as exc:
        _fail(exc)
    payload = to_response(workout)
    await db.commit()
    return payload


@router.post("/{performed_id}/finish", response_model=PerformedWorkoutResponse)
async def finish_performed(
    performed_id: uuid.UUID, user: CurrentUser, db: DbSession
) -> PerformedWorkoutResponse:
    try:
        workout = await finish(db, user.id, performed_id)
    except LogError as exc:
        _fail(exc)
    payload = to_response(workout)
    await db.commit()
    return payload


@router.post("/{performed_id}/items", response_model=PerformedWorkoutResponse)
async def add_performed_item(
    performed_id: uuid.UUID, body: ItemCreate, user: CurrentUser, db: DbSession, response: Response
) -> PerformedWorkoutResponse:
    try:
        workout, created = await add_item(db, user.id, performed_id, body)
    except LogError as exc:
        _fail(exc)
    payload = to_response(workout)
    await db.commit()
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    return payload


@router.patch("/{performed_id}/items/{item_id}", response_model=PerformedWorkoutResponse)
async def patch_item_note(
    performed_id: uuid.UUID,
    item_id: uuid.UUID,
    body: NoteWrite,
    user: CurrentUser,
    db: DbSession,
) -> PerformedWorkoutResponse:
    try:
        workout = await update_item_note(db, user.id, performed_id, item_id, body)
    except LogError as exc:
        _fail(exc)
    payload = to_response(workout)
    await db.commit()
    return payload


@router.put("/{performed_id}/items/{item_id}/exercise", response_model=PerformedWorkoutResponse)
async def put_item_exercise(
    performed_id: uuid.UUID,
    item_id: uuid.UUID,
    body: ExerciseReplace,
    user: CurrentUser,
    db: DbSession,
) -> PerformedWorkoutResponse:
    try:
        workout = await replace_exercise(db, user.id, performed_id, item_id, body)
    except LogError as exc:
        _fail(exc)
    payload = to_response(workout)
    await db.commit()
    return payload


@router.post("/{performed_id}/items/{item_id}/sets", response_model=SetLogResponse)
async def add_performed_set(
    performed_id: uuid.UUID,
    item_id: uuid.UUID,
    body: SetCreate,
    user: CurrentUser,
    db: DbSession,
    response: Response,
) -> SetLogResponse:
    try:
        logged, created = await add_set(db, user.id, performed_id, item_id, body)
    except LogError as exc:
        _fail(exc)
    payload = to_set(logged)
    await db.commit()
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    return payload


@router.put("/{performed_id}/sets/{set_id}", response_model=SetLogResponse)
async def put_set(
    performed_id: uuid.UUID,
    set_id: uuid.UUID,
    body: SetWrite,
    user: CurrentUser,
    db: DbSession,
) -> SetLogResponse:
    try:
        logged = await update_set(db, user.id, performed_id, set_id, body)
    except LogError as exc:
        _fail(exc)
    payload = to_set(logged)
    await db.commit()
    return payload


@router.delete("/{performed_id}/sets/{set_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_set(
    performed_id: uuid.UUID, set_id: uuid.UUID, user: CurrentUser, db: DbSession
) -> None:
    try:
        await delete_set(db, user.id, performed_id, set_id)
    except LogError as exc:
        _fail(exc)
    await db.commit()
