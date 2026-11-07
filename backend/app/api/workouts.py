import uuid

from fastapi import APIRouter, HTTPException, Response, status

from app.api.deps import CurrentUser, DbSession
from app.models.workout import WorkoutTemplate
from app.schemas.workout import (
    WorkoutRenameInput,
    WorkoutTemplateInput,
    WorkoutTemplateResponse,
)
from app.services.workouts import (
    ArchivedExerciseError,
    UnknownExerciseError,
    copy_template,
    create_template,
    get_template,
    list_templates,
    rename_template,
    replace_template,
)

router = APIRouter(prefix="/api/workouts", tags=["workouts"])

NOT_FOUND = "Тренировка не найдена"
UNKNOWN_EXERCISE = "Упражнение не найдено в вашем справочнике"
ARCHIVED_EXERCISE = "Упражнение в архиве. Восстановите его, чтобы добавить в тренировку"


async def _owned_or_404(
    db: DbSession, user_id: uuid.UUID, template_id: uuid.UUID
) -> WorkoutTemplate:
    template = await get_template(db, user_id, template_id)
    if template is None:
        # 404 и для чужих тренировок: не раскрываем, что такой id существует.
        raise HTTPException(status_code=404, detail=NOT_FOUND)
    return template


@router.get("", response_model=list[WorkoutTemplateResponse])
async def list_user_workouts(user: CurrentUser, db: DbSession) -> list[WorkoutTemplate]:
    return list(await list_templates(db, user.id))


@router.post("", response_model=WorkoutTemplateResponse, status_code=status.HTTP_201_CREATED)
async def create_user_workout(
    body: WorkoutTemplateInput, user: CurrentUser, db: DbSession
) -> WorkoutTemplate:
    try:
        template = await create_template(db, user.id, body)
    except UnknownExerciseError:
        raise HTTPException(status_code=422, detail=UNKNOWN_EXERCISE) from None
    except ArchivedExerciseError:
        raise HTTPException(status_code=422, detail=ARCHIVED_EXERCISE) from None
    await db.commit()
    return template


@router.get("/{workout_id}", response_model=WorkoutTemplateResponse)
async def get_user_workout(
    workout_id: uuid.UUID, user: CurrentUser, db: DbSession
) -> WorkoutTemplate:
    return await _owned_or_404(db, user.id, workout_id)


@router.put("/{workout_id}", response_model=WorkoutTemplateResponse)
async def update_user_workout(
    workout_id: uuid.UUID, body: WorkoutTemplateInput, user: CurrentUser, db: DbSession
) -> WorkoutTemplate:
    template = await _owned_or_404(db, user.id, workout_id)
    try:
        await replace_template(db, user.id, template, body)
    except UnknownExerciseError:
        raise HTTPException(status_code=422, detail=UNKNOWN_EXERCISE) from None
    except ArchivedExerciseError:
        raise HTTPException(status_code=422, detail=ARCHIVED_EXERCISE) from None
    await db.commit()
    return template


@router.patch("/{workout_id}", response_model=WorkoutTemplateResponse)
async def rename_user_workout(
    workout_id: uuid.UUID, body: WorkoutRenameInput, user: CurrentUser, db: DbSession
) -> WorkoutTemplate:
    template = await _owned_or_404(db, user.id, workout_id)
    rename_template(template, body.name)
    await db.commit()
    return template


@router.post(
    "/{workout_id}/copy",
    response_model=WorkoutTemplateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def copy_user_workout(
    workout_id: uuid.UUID, user: CurrentUser, db: DbSession
) -> WorkoutTemplate:
    source = await _owned_or_404(db, user.id, workout_id)
    copy = await copy_template(db, user.id, source)
    await db.commit()
    return copy


@router.delete("/{workout_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user_workout(workout_id: uuid.UUID, user: CurrentUser, db: DbSession) -> Response:
    template = await _owned_or_404(db, user.id, workout_id)
    await db.delete(template)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
