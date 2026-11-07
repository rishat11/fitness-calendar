from fastapi import APIRouter

from app.api.deps import CurrentUser, DbSession
from app.models.profile import Profile
from app.schemas.profile import ProfileResponse, ProfileUpdate
from app.services.profile import get_or_create_profile, get_profile_or_default

router = APIRouter(prefix="/api/profile", tags=["profile"])


@router.get("", response_model=ProfileResponse)
async def get_profile(user: CurrentUser, db: DbSession) -> Profile:
    return await get_profile_or_default(db, user.id)


@router.put("", response_model=ProfileResponse)
async def update_profile(body: ProfileUpdate, user: CurrentUser, db: DbSession) -> Profile:
    profile = await get_or_create_profile(db, user.id)
    for field, value in body.model_dump().items():
        setattr(profile, field, value)
    await db.commit()
    return profile
