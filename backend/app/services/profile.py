import uuid

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.profile import Profile


async def get_profile_or_default(db: AsyncSession, user_id: uuid.UUID) -> Profile:
    """Читает профиль без записи в БД: для нового пользователя возвращает значения по умолчанию.

    GET не должен менять данные; строка появится при первом PUT.
    """
    profile = await db.get(Profile, user_id)
    if profile is not None:
        return profile
    # Значения по умолчанию из модели применяются только при вставке, поэтому задаём их явно.
    return Profile(user_id=user_id, weight_unit="kg", theme="system")


async def get_or_create_profile(db: AsyncSession, user_id: uuid.UUID) -> Profile:
    """Возвращает профиль пользователя, создавая его с настройками по умолчанию при нехватке."""
    await db.execute(
        insert(Profile).values(user_id=user_id).on_conflict_do_nothing(index_elements=["user_id"])
    )
    profile = await db.get(Profile, user_id)
    if profile is None:
        raise RuntimeError("профиль не создан")
    return profile
