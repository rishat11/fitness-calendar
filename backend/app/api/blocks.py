import uuid

from fastapi import APIRouter, HTTPException, Response, status

from app.api.deps import CurrentUser, DbSession
from app.models.block import Block, BlockPlacement
from app.schemas.block import (
    BlockApplyRequest,
    BlockInput,
    BlockResponse,
    PlacementResponse,
)
from app.services.block_calendar import load_placements
from app.services.blocks import (
    BlockConflictError,
    BlockError,
    apply_block,
    copy_block,
    create_block,
    get_block,
    list_blocks,
    remove_placement,
    repeat_placement,
    replace_block,
)

router = APIRouter(prefix="/api/blocks", tags=["blocks"])

NOT_FOUND = "Блок не найден"
PLACEMENT_NOT_FOUND = "Блок в календаре не найден"


async def _owned_or_404(db: DbSession, user_id: uuid.UUID, block_id: uuid.UUID) -> Block:
    block = await get_block(db, user_id, block_id)
    if block is None:
        # 404 и для чужих блоков: не раскрываем, что такой id существует.
        raise HTTPException(status_code=404, detail=NOT_FOUND)
    return block


@router.get("", response_model=list[BlockResponse])
async def list_user_blocks(user: CurrentUser, db: DbSession) -> list[Block]:
    return list(await list_blocks(db, user.id))


@router.post("", response_model=BlockResponse, status_code=status.HTTP_201_CREATED)
async def create_user_block(body: BlockInput, user: CurrentUser, db: DbSession) -> Block:
    try:
        block = await create_block(db, user.id, body)
    except BlockError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    await db.commit()
    return block


@router.get("/placements", response_model=list[PlacementResponse])
async def list_user_placements(user: CurrentUser, db: DbSession) -> list[BlockPlacement]:
    return await load_placements(db, user.id)


@router.post("/placements/{placement_id}/repeat", response_model=PlacementResponse)
async def repeat_user_placement(
    placement_id: uuid.UUID, user: CurrentUser, db: DbSession
) -> BlockPlacement:
    placement = next(
        (item for item in await load_placements(db, user.id) if item.id == placement_id),
        None,
    )
    if placement is None:
        raise HTTPException(status_code=404, detail=PLACEMENT_NOT_FOUND)
    try:
        await repeat_placement(db, user.id, placement)
    except BlockConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    except BlockError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    await db.commit()
    return placement


@router.delete("/placements/{placement_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_user_placement(
    placement_id: uuid.UUID, user: CurrentUser, db: DbSession
) -> Response:
    placement = next(
        (item for item in await load_placements(db, user.id) if item.id == placement_id),
        None,
    )
    if placement is None:
        raise HTTPException(status_code=404, detail=PLACEMENT_NOT_FOUND)
    await remove_placement(db, user.id, placement)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{block_id}", response_model=BlockResponse)
async def get_user_block(block_id: uuid.UUID, user: CurrentUser, db: DbSession) -> Block:
    return await _owned_or_404(db, user.id, block_id)


@router.put("/{block_id}", response_model=BlockResponse)
async def update_user_block(
    block_id: uuid.UUID, body: BlockInput, user: CurrentUser, db: DbSession
) -> Block:
    block = await _owned_or_404(db, user.id, block_id)
    try:
        await replace_block(db, user.id, block, body)
    except BlockError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    await db.commit()
    return block


@router.delete("/{block_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user_block(block_id: uuid.UUID, user: CurrentUser, db: DbSession) -> Response:
    block = await _owned_or_404(db, user.id, block_id)
    await db.delete(block)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{block_id}/copy",
    response_model=BlockResponse,
    status_code=status.HTTP_201_CREATED,
)
async def copy_user_block(block_id: uuid.UUID, user: CurrentUser, db: DbSession) -> Block:
    source = await _owned_or_404(db, user.id, block_id)
    copy = await copy_block(db, user.id, source)
    await db.commit()
    return copy


@router.post(
    "/{block_id}/apply",
    response_model=PlacementResponse,
    status_code=status.HTTP_201_CREATED,
)
async def apply_user_block(
    block_id: uuid.UUID, body: BlockApplyRequest, user: CurrentUser, db: DbSession
) -> BlockPlacement:
    block = await _owned_or_404(db, user.id, block_id)
    try:
        placement = await apply_block(db, user.id, block, body.start_date, repeats=body.repeats)
    except BlockConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    await db.commit()
    return placement
