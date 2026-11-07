import uuid
from collections.abc import Sequence

from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.exercise import Exercise
from app.models.workout import WorkoutTemplate, WorkoutTemplateItem, WorkoutTemplateSet
from app.schemas.workout import WorkoutTemplateInput

COPY_SUFFIX = " (копия)"
NAME_MAX = 120


class UnknownExerciseError(Exception):
    """Упражнение не найдено в справочнике пользователя."""


async def list_templates(db: AsyncSession, user_id: uuid.UUID) -> Sequence[WorkoutTemplate]:
    result = await db.scalars(
        select(WorkoutTemplate)
        .where(WorkoutTemplate.user_id == user_id)
        .order_by(WorkoutTemplate.created_at, WorkoutTemplate.id)
    )
    return result.all()


async def get_template(
    db: AsyncSession, user_id: uuid.UUID, template_id: uuid.UUID
) -> WorkoutTemplate | None:
    """Возвращает тренировку только если она принадлежит пользователю."""
    return await db.scalar(
        select(WorkoutTemplate).where(
            WorkoutTemplate.id == template_id, WorkoutTemplate.user_id == user_id
        )
    )


async def exercise_is_in_templates(db: AsyncSession, exercise_id: uuid.UUID) -> bool:
    return bool(
        await db.scalar(select(exists().where(WorkoutTemplateItem.exercise_id == exercise_id)))
    )


async def _owned_exercises(
    db: AsyncSession,
    user_id: uuid.UUID,
    exercise_ids: set[uuid.UUID],
) -> dict[uuid.UUID, Exercise]:
    """Проверяет, что каждое упражнение есть в справочнике этого пользователя."""
    if not exercise_ids:
        return {}
    result = await db.scalars(
        select(Exercise).where(Exercise.id.in_(exercise_ids), Exercise.user_id == user_id)
    )
    found = {exercise.id: exercise for exercise in result}
    if len(found) != len(exercise_ids):
        raise UnknownExerciseError
    return found


def _build_items(
    data: WorkoutTemplateInput, exercises: dict[uuid.UUID, Exercise]
) -> list[WorkoutTemplateItem]:
    items: list[WorkoutTemplateItem] = []
    for position, item_data in enumerate(data.items):
        item = WorkoutTemplateItem(
            exercise_id=item_data.exercise_id,
            exercise=exercises[item_data.exercise_id],
            position=position,
        )
        item.sets = [
            WorkoutTemplateSet(
                position=set_position,
                rep_min=set_data.rep_min,
                rep_max=set_data.rep_max,
                target_rir=set_data.target_rir,
                rest_seconds=set_data.rest_seconds,
            )
            for set_position, set_data in enumerate(item_data.sets)
        ]
        items.append(item)
    return items


async def create_template(
    db: AsyncSession, user_id: uuid.UUID, data: WorkoutTemplateInput
) -> WorkoutTemplate:
    exercises = await _owned_exercises(db, user_id, {item.exercise_id for item in data.items})
    template = WorkoutTemplate(user_id=user_id, name=data.name, items=_build_items(data, exercises))
    db.add(template)
    await db.flush()
    return template


async def replace_template(
    db: AsyncSession, user_id: uuid.UUID, template: WorkoutTemplate, data: WorkoutTemplateInput
) -> WorkoutTemplate:
    """Заменяет название и все позиции. Старые позиции и подходы удаляются каскадом.

    Идентификаторы позиций и подходов при этом меняются. Ссылок на них вне библиотеки нет:
    план и журнал будут хранить снимок (шаг 4), поэтому правка шаблона их не затронет.
    """
    exercises = await _owned_exercises(db, user_id, {item.exercise_id for item in data.items})
    template.name = data.name
    template.items = _build_items(data, exercises)
    await db.flush()
    return template


def rename_template(template: WorkoutTemplate, name: str) -> WorkoutTemplate:
    template.name = name
    return template


async def copy_template(
    db: AsyncSession, user_id: uuid.UUID, source: WorkoutTemplate
) -> WorkoutTemplate:
    suffix_room = NAME_MAX - len(COPY_SUFFIX)
    copy = WorkoutTemplate(
        user_id=user_id,
        name=source.name[:suffix_room] + COPY_SUFFIX,
        items=[
            WorkoutTemplateItem(
                exercise_id=item.exercise_id,
                exercise=item.exercise,
                position=item.position,
                sets=[
                    WorkoutTemplateSet(
                        position=set_.position,
                        rep_min=set_.rep_min,
                        rep_max=set_.rep_max,
                        target_rir=set_.target_rir,
                        rest_seconds=set_.rest_seconds,
                    )
                    for set_ in item.sets
                ],
            )
            for item in source.items
        ],
    )
    db.add(copy)
    await db.flush()
    return copy
