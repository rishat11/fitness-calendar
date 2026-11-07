import uuid
from typing import Annotated

from fastapi import APIRouter, File, HTTPException, Response, UploadFile, status

from app.api.deps import CurrentUser, DbSession
from app.models.inbody import InbodyScan
from app.schemas.inbody import (
    InbodyParseResponse,
    InbodyScanInput,
    InbodyScanResponse,
    MetricDeltaResponse,
)
from app.schemas.nutrition import number_from_decimal
from app.services.inbody import (
    MetricDelta,
    attach_comparisons,
    comparison_for,
    create_scan,
    get_scan,
    list_scans,
    replace_scan,
)
from app.services.inbody_pdf import InbodyPdfError, ParsedSheet, parse_inbody_pdf

_MAX_PDF_BYTES = 8 * 1024 * 1024
PdfUpload = Annotated[UploadFile, File()]

router = APIRouter(prefix="/api/inbody", tags=["inbody"])

NOT_FOUND = "Замер не найден"


def _parse_response(sheet: ParsedSheet) -> InbodyParseResponse:
    return InbodyParseResponse(
        measured_on=sheet.measured_on,
        measured_time=sheet.measured_time,
        weight_kg=number_from_decimal(sheet.weight_kg),
        smm_kg=number_from_decimal(sheet.smm_kg),
        bfm_kg=number_from_decimal(sheet.bfm_kg),
        pbf_percent=number_from_decimal(sheet.pbf_percent),
        tbw_l=number_from_decimal(sheet.tbw_l),
        visceral_fat_level=sheet.visceral_fat_level,
        bmr_kcal=sheet.bmr_kcal,
        missing=list(sheet.missing()),
    )


def _delta_response(delta: MetricDelta) -> MetricDeltaResponse:
    absolute = number_from_decimal(delta.absolute)
    if absolute is None:
        absolute = 0
    return MetricDeltaResponse(
        code=delta.code,  # type: ignore[arg-type]
        absolute=absolute,
        relative_percent=number_from_decimal(delta.relative_percent),
        unit=delta.unit,  # type: ignore[arg-type]
    )


def _response(row: InbodyScan, *, deltas: tuple[MetricDelta, ...]) -> InbodyScanResponse:
    return InbodyScanResponse.model_validate(
        {
            "id": row.id,
            "measured_on": row.measured_on,
            "measured_time": row.measured_time,
            "weight_kg": number_from_decimal(row.weight_kg),
            "smm_kg": number_from_decimal(row.smm_kg),
            "bfm_kg": number_from_decimal(row.bfm_kg),
            "pbf_percent": number_from_decimal(row.pbf_percent),
            "tbw_l": number_from_decimal(row.tbw_l),
            "visceral_fat_level": row.visceral_fat_level,
            "bmr_kcal": row.bmr_kcal,
            "segments": row.segments,
            "deltas": [_delta_response(delta) for delta in deltas],
        }
    )


async def _owned_or_404(db: DbSession, user_id: uuid.UUID, scan_id: uuid.UUID) -> InbodyScan:
    row = await get_scan(db, user_id, scan_id)
    if row is None:
        raise HTTPException(status_code=404, detail=NOT_FOUND)
    return row


@router.get("", response_model=list[InbodyScanResponse])
async def list_user_scans(user: CurrentUser, db: DbSession) -> list[InbodyScanResponse]:
    rows = await list_scans(db, user.id)
    return [_response(row, deltas=deltas) for row, deltas in attach_comparisons(rows)]


@router.post("/parse", response_model=InbodyParseResponse)
async def parse_user_sheet(user: CurrentUser, file: PdfUpload) -> InbodyParseResponse:
    """Читает PDF и возвращает цифры. Строку замера не создаёт."""
    del user
    raw = await file.read(_MAX_PDF_BYTES + 1)
    if len(raw) > _MAX_PDF_BYTES:
        raise HTTPException(status_code=422, detail="Файл больше 8 МБ")
    try:
        sheet = parse_inbody_pdf(raw)
    except InbodyPdfError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _parse_response(sheet)


@router.post("", response_model=InbodyScanResponse, status_code=status.HTTP_201_CREATED)
async def create_user_scan(
    body: InbodyScanInput, user: CurrentUser, db: DbSession
) -> InbodyScanResponse:
    row = await create_scan(db, user.id, body)
    await db.commit()
    _row, deltas = comparison_for(await list_scans(db, user.id), row.id)
    return _response(_row, deltas=deltas)


@router.put("/{scan_id}", response_model=InbodyScanResponse)
async def update_user_scan(
    scan_id: uuid.UUID, body: InbodyScanInput, user: CurrentUser, db: DbSession
) -> InbodyScanResponse:
    row = await _owned_or_404(db, user.id, scan_id)
    await replace_scan(row, body)
    await db.commit()
    _row, deltas = comparison_for(await list_scans(db, user.id), row.id)
    return _response(_row, deltas=deltas)


@router.delete("/{scan_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user_scan(scan_id: uuid.UUID, user: CurrentUser, db: DbSession) -> Response:
    row = await _owned_or_404(db, user.id, scan_id)
    await db.delete(row)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
