import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.exercise import Exercise
from app.schemas.exercise import ExerciseInput


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


async def list_exercises(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    query: str | None = None,
) -> Sequence[Exercise]:
    stmt = select(Exercise).where(Exercise.user_id == user_id)
    if query:
        stmt = stmt.where(Exercise.name.ilike(f"%{_escape_like(query.strip())}%", escape="\\"))
    stmt = stmt.order_by(func.lower(Exercise.name))
    result = await db.scalars(stmt)
    return result.all()


async def get_exercise(
    db: AsyncSession, user_id: uuid.UUID, exercise_id: uuid.UUID
) -> Exercise | None:
    """Возвращает упражнение только если оно принадлежит пользователю."""
    return await db.scalar(
        select(Exercise).where(Exercise.id == exercise_id, Exercise.user_id == user_id)
    )


def _apply(exercise: Exercise, data: ExerciseInput) -> None:
    for field, value in data.model_dump().items():
        setattr(exercise, field, value)


async def create_exercise(db: AsyncSession, user_id: uuid.UUID, data: ExerciseInput) -> Exercise:
    exercise = Exercise(user_id=user_id)
    _apply(exercise, data)
    db.add(exercise)
    await db.flush()
    return exercise


def replace_exercise(exercise: Exercise, data: ExerciseInput) -> Exercise:
    _apply(exercise, data)
    return exercise
