import uuid

from fastapi import APIRouter, HTTPException, Query, Response, status

from app.api.deps import CurrentUser, DbSession
from app.models.exercise import Exercise
from app.schemas.exercise import ExerciseHistory, ExerciseInput, ExerciseResponse
from app.services.exercise_history import exercise_history
from app.services.exercises import (
    create_exercise,
    get_exercise,
    list_exercises,
    replace_exercise,
)
from app.services.workouts import exercise_is_in_templates

router = APIRouter(prefix="/api/exercises", tags=["exercises"])

NOT_FOUND = "Упражнение не найдено"
IN_USE = "Упражнение входит в тренировки. Сначала уберите его оттуда."


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
    q: str | None = Query(default=None, max_length=120),
) -> list[Exercise]:
    exercises = await list_exercises(db, user.id, query=q)
    return list(exercises)


@router.post("", response_model=ExerciseResponse, status_code=status.HTTP_201_CREATED)
async def create_user_exercise(body: ExerciseInput, user: CurrentUser, db: DbSession) -> Exercise:
    exercise = await create_exercise(db, user.id, body)
    await db.commit()
    return exercise


@router.get("/{exercise_id}/history", response_model=ExerciseHistory)
async def read_exercise_history(
    exercise_id: uuid.UUID, user: CurrentUser, db: DbSession
) -> ExerciseHistory:
    history = await exercise_history(db, user.id, exercise_id)
    if history is None:
        raise HTTPException(status_code=404, detail=NOT_FOUND)
    return history


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
