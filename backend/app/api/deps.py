from datetime import UTC, datetime
from typing import Annotated

from fastapi import Cookie, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.user import Session, User
from app.services.auth import hash_token, open_token, purge_expired_sessions

SESSION_COOKIE = "session_id"

DbSession = Annotated[AsyncSession, Depends(get_db)]


async def get_current_user(
    db: DbSession,
    session_id: str | None = Cookie(default=None, alias=SESSION_COOKIE),
) -> User:
    if not session_id:
        raise HTTPException(status_code=401, detail="Требуется вход")
    raw = open_token(session_id)
    if raw is None:
        raise HTTPException(status_code=401, detail="Требуется вход")
    now = datetime.now(UTC)
    user = await db.scalar(
        select(User)
        .join(Session, Session.user_id == User.id)
        .where(Session.token_hash == hash_token(raw), Session.expires_at > now)
    )
    if user is None:
        await purge_expired_sessions(db)
        await db.commit()
        raise HTTPException(status_code=401, detail="Требуется вход")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
