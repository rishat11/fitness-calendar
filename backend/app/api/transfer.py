from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query, Response

from app.api.deps import CurrentUser, DbSession
from app.schemas.transfer import ExportDocument, ImportResult
from app.services.transfer import (
    TransferError,
    build_export,
    import_replace,
    mark_exported,
    workouts_csv,
)

router = APIRouter(prefix="/api", tags=["transfer"])


@router.get("/export", response_model=ExportDocument)
async def export_data(user: CurrentUser, db: DbSession) -> ExportDocument:
    """Все данные пользователя: справочник, шаблоны, план, журнал сдвигов и факт тренировок."""
    document = await build_export(db, user.id)
    await mark_exported(db, user.id, document.exported_at)
    await db.commit()
    return document


@router.get("/export/workouts.csv")
async def export_workouts_csv(user: CurrentUser, db: DbSession) -> Response:
    """Тренировки в CSV: одна строка на подход. Замеры появятся вместе с InBody."""
    document = await build_export(db, user.id)
    return Response(
        content=workouts_csv(document),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="workouts.csv"'},
    )


@router.post("/import", response_model=ImportResult)
async def import_data(
    body: ExportDocument,
    user: CurrentUser,
    db: DbSession,
    mode: Annotated[
        Literal["replace"],
        Query(description="Единственный режим: заменить данные аккаунта"),
    ],
) -> ImportResult:
    """Проверяет файл и в одной транзакции заменяет данные. Чужие идентификаторы получают новые."""
    try:
        result = await import_replace(db, user.id, body)
    except TransferError as exc:
        await db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from None
    await db.commit()
    return result
