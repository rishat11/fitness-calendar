from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException, Request, Response, status
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from app.api.deps import SESSION_COOKIE, CurrentUser, DbSession
from app.config import settings
from app.models.user import Session, User
from app.models.workout import WorkoutTemplate
from app.schemas.auth import DeleteAccountRequest, LoginRequest, RegisterRequest, UserResponse
from app.services.auth import (
    dummy_verify,
    hash_password,
    hash_token,
    new_session_token,
    normalize_email,
    open_token,
    purge_expired_sessions,
    verify_password,
)
from app.services.rate_limit import client_ip, login_is_limited, record_login_failure

# Префикс /api нужен прокси Vite: браузер ходит на тот же origin, cookie не упирается в CORS.
# В шаге 3 пути записаны как /auth/*; рабочие пути — /api/auth/*.
router = APIRouter(prefix="/api/auth", tags=["auth"])

_EMAIL_TAKEN = "Пользователь с таким email уже зарегистрирован"
_BAD_CREDENTIALS = "Неверный email или пароль"
_BAD_PASSWORD = "Неверный пароль"
_TOO_MANY_ATTEMPTS = "Слишком много попыток входа. Попробуйте позже."


def set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
        max_age=settings.session_ttl_days * 24 * 60 * 60,
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(
        key=SESSION_COOKIE,
        path="/",
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
    )


async def _issue_session(db: DbSession, user: User, response: Response) -> None:
    token, token_hash = new_session_token()
    await purge_expired_sessions(db)
    db.add(
        Session(
            user_id=user.id,
            token_hash=token_hash,
            expires_at=datetime.now(UTC) + timedelta(days=settings.session_ttl_days),
        )
    )
    await db.commit()
    set_session_cookie(response, token)


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest, response: Response, db: DbSession) -> User:
    # 409 называет занятый email. Для личного сервиса это понятнее, чем одинаковый ответ,
    # но по коду можно узнать, зарегистрирован ли адрес.
    email = normalize_email(str(body.email))
    existing = await db.scalar(select(User.id).where(User.email == email))
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=_EMAIL_TAKEN)
    user = User(email=email, password_hash=hash_password(body.password))
    db.add(user)
    try:
        await db.flush()
        await _issue_session(db, user, response)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=_EMAIL_TAKEN) from None
    return user


@router.post("/login", response_model=UserResponse)
async def login(body: LoginRequest, request: Request, response: Response, db: DbSession) -> User:
    email = normalize_email(str(body.email))
    ip = client_ip(request)
    if login_is_limited(ip, email):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=_TOO_MANY_ATTEMPTS,
        )
    user = await db.scalar(select(User).where(User.email == email))
    password_ok = verify_password(body.password, user.password_hash) if user is not None else False
    if user is None:
        dummy_verify(body.password)
    if user is None or not password_ok:
        record_login_failure(ip, email)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=_BAD_CREDENTIALS)
    await _issue_session(db, user, response)
    return user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request, response: Response, db: DbSession) -> None:
    token = request.cookies.get(SESSION_COOKIE)
    raw = open_token(token) if token else None
    if raw:
        await db.execute(delete(Session).where(Session.token_hash == hash_token(raw)))
    await purge_expired_sessions(db)
    await db.commit()
    clear_session_cookie(response)


@router.get("/me", response_model=UserResponse)
async def me(user: CurrentUser) -> User:
    return user


@router.delete("/account", status_code=status.HTTP_204_NO_CONTENT)
async def delete_account(
    body: DeleteAccountRequest,
    request: Request,
    response: Response,
    user: CurrentUser,
    db: DbSession,
) -> None:
    # Тот же лимит, что у входа: украденная сессия не должна перебирать пароль.
    email = user.email
    ip = client_ip(request)
    if login_is_limited(ip, email):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=_TOO_MANY_ATTEMPTS,
        )
    if not verify_password(body.password, user.password_hash):
        record_login_failure(ip, email)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=_BAD_PASSWORD)
    # Пункты шаблона ссылаются на упражнения с RESTRICT. Сначала шаблоны, потом пользователь:
    # остальное (сессии, профиль, упражнения, план, журнал) уходит каскадом базы.
    await db.execute(delete(WorkoutTemplate).where(WorkoutTemplate.user_id == user.id))
    await db.flush()
    await db.delete(user)
    await db.commit()
    clear_session_cookie(response)
