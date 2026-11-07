import hashlib
import hmac
import secrets
from datetime import UTC, datetime

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.user import Session

_hasher = PasswordHasher()
_DUMMY_PASSWORD_HASH = _hasher.hash("not-a-real-password")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def dummy_verify(password: str) -> None:
    verify_password(password, _DUMMY_PASSWORD_HASH)


def new_session_token() -> tuple[str, str]:
    raw = secrets.token_urlsafe(32)
    return seal_token(raw), hash_token(raw)


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def seal_token(raw: str) -> str:
    return f"{raw}.{_sign(raw)}"


def open_token(token: str) -> str | None:
    raw, separator, signature = token.rpartition(".")
    if separator != "." or not raw or len(signature) != 64:
        return None
    if not hmac.compare_digest(_sign(raw), signature):
        return None
    return raw


def normalize_email(email: str) -> str:
    return email.strip().lower()


async def purge_expired_sessions(db: AsyncSession) -> None:
    await db.execute(delete(Session).where(Session.expires_at <= datetime.now(UTC)))


def _sign(raw: str) -> str:
    return hmac.new(settings.secret_key.encode(), raw.encode(), hashlib.sha256).hexdigest()
