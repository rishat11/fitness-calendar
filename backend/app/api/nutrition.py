from fastapi import APIRouter

from app.api.deps import CurrentUser, DbSession
from app.schemas.nutrition import (
    IntakeResponse,
    IntakeUpdate,
    MacroTargetResponse,
    number_from_decimal,
)
from app.services.nutrition import (
    IntakeView,
    MacroTargetView,
    current_macro_target,
    get_intake,
    present_intake,
    save_intake,
)

router = APIRouter(prefix="/api/nutrition", tags=["nutrition"])


def _intake_response(view: IntakeView) -> IntakeResponse:
    return IntakeResponse(
        protein_g=number_from_decimal(view.protein_g),
        fat_g=number_from_decimal(view.fat_g),
        carbs_g=number_from_decimal(view.carbs_g),
        calories=number_from_decimal(view.calories),
    )


def _target_response(view: MacroTargetView) -> MacroTargetResponse:
    return MacroTargetResponse(
        available=view.available,
        reason=view.reason,
        protein_g=number_from_decimal(view.protein_g),
        fat_g=number_from_decimal(view.fat_g),
        carbs_g=number_from_decimal(view.carbs_g),
        calories=view.calories,
    )


@router.get("/intake", response_model=IntakeResponse)
async def read_intake(user: CurrentUser, db: DbSession) -> IntakeResponse:
    # Нет строки — пустые граммы. Запись появится только при PUT.
    return _intake_response(present_intake(await get_intake(db, user.id)))


@router.put("/intake", response_model=IntakeResponse)
async def update_intake(body: IntakeUpdate, user: CurrentUser, db: DbSession) -> IntakeResponse:
    row = await save_intake(
        db,
        user.id,
        protein_g=body.protein_g,
        fat_g=body.fat_g,
        carbs_g=body.carbs_g,
    )
    await db.commit()
    return _intake_response(present_intake(row))


@router.get("/targets", response_model=MacroTargetResponse)
async def read_macro_target(user: CurrentUser, db: DbSession) -> MacroTargetResponse:
    """Цель по последнему замеру. Без замера или цели отдаёт причину и ничего не записывает."""
    return _target_response(await current_macro_target(db, user.id))
