import datetime as dt
import uuid
from typing import Annotated, NoReturn, cast

from fastapi import APIRouter, HTTPException, Query, Response, status

from app.api.deps import CurrentUser, DbSession
from app.models.plan import PlannedWorkout
from app.models.workout import WorkoutTemplate
from app.schemas.plan import (
    PlanChangeLogItem,
    PlanCycleCreate,
    PlanEntryCreate,
    PlanEntryResponse,
    PlanEntryUpdate,
    PlanKind,
    PlanShiftChange,
    PlanShiftConflict,
    PlanShiftPreview,
    PlanShiftRequest,
    PlanShiftResult,
    PlanStatus,
    ShiftOperation,
    ShiftResolution,
)
from app.services.plan import (
    MAX_RANGE_DAYS,
    PlanConflictError,
    create_cycle,
    create_entry,
    create_rest,
    delete_entry,
    get_entry,
    list_entries,
    update_entry,
)
from app.services.plan_shift import (
    ShiftConflictError,
    ShiftError,
    ShiftPlan,
    apply_shift,
    list_shift_history,
    preview_shift,
    undo_last_shift,
)
from app.services.workouts import get_template

router = APIRouter(prefix="/api/plan", tags=["plan"])

NOT_FOUND = "Запись плана не найдена"
UNKNOWN_TEMPLATE = "Тренировка не найдена в вашей библиотеке"
BAD_RANGE = "Некорректный диапазон дат"


async def _owned_entry_or_404(
    db: DbSession, user_id: uuid.UUID, entry_id: uuid.UUID
) -> PlannedWorkout:
    entry = await get_entry(db, user_id, entry_id)
    if entry is None:
        # 404 и для чужих записей: не раскрываем, что такой id существует.
        raise HTTPException(status_code=404, detail=NOT_FOUND)
    return entry


async def _owned_template_or_422(
    db: DbSession, user_id: uuid.UUID, template_id: uuid.UUID
) -> WorkoutTemplate:
    template = await get_template(db, user_id, template_id)
    if template is None:
        raise HTTPException(status_code=422, detail=UNKNOWN_TEMPLATE)
    return template


@router.get("", response_model=list[PlanEntryResponse])
async def list_plan(
    user: CurrentUser,
    db: DbSession,
    start: Annotated[dt.date, Query()],
    end: Annotated[dt.date, Query()],
) -> list[PlannedWorkout]:
    if end < start or (end - start).days >= MAX_RANGE_DAYS:
        raise HTTPException(status_code=422, detail=BAD_RANGE)
    return list(await list_entries(db, user.id, start, end))


@router.post("/entries", response_model=PlanEntryResponse, status_code=status.HTTP_201_CREATED)
async def add_plan_entry(body: PlanEntryCreate, user: CurrentUser, db: DbSession) -> PlannedWorkout:
    try:
        if body.kind == "rest":
            entry = await create_rest(db, user.id, body.date)
        elif body.template_id is not None:
            template = await _owned_template_or_422(db, user.id, body.template_id)
            entry = await create_entry(db, user.id, body.date, template=template)
        else:
            entry = await create_entry(db, user.id, body.date, name=body.name)
    except PlanConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    await db.commit()
    return entry


@router.post(
    "/cycles",
    response_model=list[PlanEntryResponse],
    status_code=status.HTTP_201_CREATED,
)
async def add_plan_cycle(
    body: PlanCycleCreate, user: CurrentUser, db: DbSession
) -> list[PlannedWorkout]:
    template = await _owned_template_or_422(db, user.id, body.template_id)
    try:
        entries = await create_cycle(
            db,
            user.id,
            template,
            start=body.start_date,
            weekdays=set(body.weekdays),
            weeks=body.weeks,
        )
    except PlanConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    await db.commit()
    return entries


def _shift_changes(plan: ShiftPlan) -> list[PlanShiftChange]:
    return [
        PlanShiftChange(
            id=change.id,
            name=change.name,
            kind=cast(PlanKind, change.kind),
            date_before=change.date_before,
            date_after=change.date_after,
            status_before=cast(PlanStatus | None, change.status_before),
            status_after=cast(PlanStatus | None, change.status_after),
        )
        for change in plan.changes
    ]


def _shift_preview(plan: ShiftPlan) -> PlanShiftPreview:
    return PlanShiftPreview(
        changes=_shift_changes(plan),
        conflicts=[
            PlanShiftConflict(
                entry_id=conflict.entry_id,
                date=conflict.date,
                reason=conflict.reason,
                message=conflict.message,
            )
            for conflict in plan.conflicts
        ],
        resolutions=[cast(ShiftResolution, item) for item in plan.resolutions],
    )


def _raise_shift_error(exc: ShiftError) -> NoReturn:
    status_code = status.HTTP_404_NOT_FOUND if exc.missing else 422
    raise HTTPException(status_code=status_code, detail=str(exc)) from None


@router.post("/shift/preview", response_model=PlanShiftPreview)
async def preview_plan_shift(
    body: PlanShiftRequest, user: CurrentUser, db: DbSession
) -> PlanShiftPreview:
    try:
        plan = await preview_shift(
            db,
            user.id,
            operation=body.operation,
            anchor_id=body.entry_id,
            days=body.days,
            other_id=body.other_id,
            resolution=body.resolution,
        )
    except ShiftError as exc:
        _raise_shift_error(exc)
    return _shift_preview(plan)


@router.post("/shift/apply", response_model=PlanShiftResult)
async def apply_plan_shift(
    body: PlanShiftRequest, user: CurrentUser, db: DbSession
) -> PlanShiftResult:
    try:
        plan, log_id = await apply_shift(
            db,
            user.id,
            operation=body.operation,
            anchor_id=body.entry_id,
            days=body.days,
            other_id=body.other_id,
            resolution=body.resolution,
        )
    except ShiftError as exc:
        _raise_shift_error(exc)
    except ShiftConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from None
    await db.commit()
    return PlanShiftResult(applied=log_id is not None, changes=_shift_changes(plan), log_id=log_id)


@router.post("/shift/undo", response_model=PlanShiftResult)
async def undo_plan_shift(user: CurrentUser, db: DbSession) -> PlanShiftResult:
    try:
        plan, log_id = await undo_last_shift(db, user.id)
    except ShiftError as exc:
        _raise_shift_error(exc)
    except ShiftConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from None
    await db.commit()
    return PlanShiftResult(applied=True, changes=_shift_changes(plan), log_id=log_id)


@router.get("/shift/history", response_model=list[PlanChangeLogItem])
async def plan_shift_history(user: CurrentUser, db: DbSession) -> list[PlanChangeLogItem]:
    logs = await list_shift_history(db, user.id)
    return [
        PlanChangeLogItem(
            id=log.id,
            created_at=log.created_at,
            operation=cast(ShiftOperation, log.operation),
            change_count=len(log.payload["changes"]),
        )
        for log in logs
    ]


@router.patch("/{entry_id}", response_model=PlanEntryResponse)
async def update_plan_entry(
    entry_id: uuid.UUID, body: PlanEntryUpdate, user: CurrentUser, db: DbSession
) -> PlannedWorkout:
    entry = await _owned_entry_or_404(db, user.id, entry_id)
    try:
        await update_entry(
            db,
            user.id,
            entry,
            day=body.date,
            status=body.status,
            is_fixed=body.is_fixed,
        )
    except PlanConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    await db.commit()
    return entry


@router.delete("/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_plan_entry(entry_id: uuid.UUID, user: CurrentUser, db: DbSession) -> Response:
    entry = await _owned_entry_or_404(db, user.id, entry_id)
    await delete_entry(db, entry)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
