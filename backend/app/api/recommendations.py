from fastapi import APIRouter

from app.api.deps import CurrentUser, DbSession
from app.schemas.recommendations import BasisItem, RecommendationItem, RecommendationsResponse
from app.services.recommendations import DISCLAIMER, collect_recommendations

router = APIRouter(prefix="/api/recommendations", tags=["recommendations"])


@router.get("", response_model=RecommendationsResponse)
async def read_recommendations(user: CurrentUser, db: DbSession) -> RecommendationsResponse:
    """Считает выводы по своим данным и ничего не записывает."""
    items = await collect_recommendations(db, user.id)
    return RecommendationsResponse(
        disclaimer=DISCLAIMER,
        items=[
            RecommendationItem(
                code=item.code,  # type: ignore[arg-type]
                text=item.text,
                basis=[BasisItem(label=row.label, value=row.value) for row in item.basis],
            )
            for item in items
        ],
    )
