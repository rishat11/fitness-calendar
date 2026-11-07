import uuid

from fastapi import APIRouter, HTTPException, Query, Response, status

from app.api.deps import CurrentUser, DbSession
from app.models.exercise import Exercise
from app.schemas.exercise import ExerciseInput, ExerciseResponse
from app.services.exercises import (
    create_exercise,
    get_exercise,
    list_exercises,
    replace_exercise,
)
from app.services.workouts import exercise_is_in_templates

router = APIRouter(prefix="/api/exercises", tags=["exercises"])

NOT_FOUND = "Упражнение не найдено"
IN_USE = "Упражнение входит в тренировки. Его можно только отправить в архив."


async def _owned_or_404(db: DbSession, user_id: uuid.UUID, exercise_id: uuid.UUID) -> Exercise:
    exercise = await get_exercise(db, user_id, exercise_id)
    if exercise is None:
        # 404 и для чужих упражнений: не раскрываем, что такой id существует.
        raise HTTPException(status_code=404, detail=NOT_FOUND)
    return exercise


@router.get("", response_model=list[ExerciseResponse])
async def list_user_exercises(
    user: CurrentUser,
    db: DbSession,
    include_archived: bool = False,
    q: str | None = Query(default=None, max_length=120),
) -> list[Exercise]:
    exercises = await list_exercises(db, user.id, include_archived=include_archived, query=q)
    return list(exercises)


@router.post("", response_model=ExerciseResponse, status_code=status.HTTP_201_CREATED)
async def create_user_exercise(body: ExerciseInput, user: CurrentUser, db: DbSession) -> Exercise:
    exercise = await create_exercise(db, user.id, body)
    await db.commit()
    return exercise


@router.get("/{exercise_id}", response_model=ExerciseResponse)
async def get_user_exercise(exercise_id: uuid.UUID, user: CurrentUser, db: DbSession) -> Exercise:
    return await _owned_or_404(db, user.id, exercise_id)


@router.put("/{exercise_id}", response_model=ExerciseResponse)
async def update_user_exercise(
    exercise_id: uuid.UUID, body: ExerciseInput, user: CurrentUser, db: DbSession
) -> Exercise:
    exercise = await _owned_or_404(db, user.id, exercise_id)
    replace_exercise(exercise, body)
    await db.commit()
    return exercise


@router.delete("/{exercise_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user_exercise(
    exercise_id: uuid.UUID, user: CurrentUser, db: DbSession
) -> Response:
    exercise = await _owned_or_404(db, user.id, exercise_id)
    if await exercise_is_in_templates(db, exercise.id):
        raise HTTPException(status_code=409, detail=IN_USE)
    await db.delete(exercise)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{exercise_id}/archive", response_model=ExerciseResponse)
async def archive_user_exercise(
    exercise_id: uuid.UUID, user: CurrentUser, db: DbSession
) -> Exercise:
    exercise = await _owned_or_404(db, user.id, exercise_id)
    exercise.archived = True
    await db.commit()
    return exercise


@router.post("/{exercise_id}/restore", response_model=ExerciseResponse)
async def restore_user_exercise(
    exercise_id: uuid.UUID, user: CurrentUser, db: DbSession
) -> Exercise:
    exercise = await _owned_or_404(db, user.id, exercise_id)
    exercise.archived = False
    await db.commit()
    return exercise
