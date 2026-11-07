from datetime import UTC, datetime, timedelta

from app.models.user import Session
from httpx import AsyncClient
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession


async def test_register_logs_in(client: AsyncClient) -> None:
    response = await client.post(
        "/api/auth/register",
        json={"email": "user@example.com", "password": "password1"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "user@example.com"
    assert set(body) == {"id", "email", "created_at"}
    cookie = response.headers["set-cookie"].lower()
    assert "session_id=" in cookie
    assert "httponly" in cookie
    assert "samesite=lax" in cookie

    me = await client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["email"] == "user@example.com"


async def test_register_duplicate_email_is_case_insensitive(client: AsyncClient) -> None:
    first = await client.post(
        "/api/auth/register",
        json={"email": "User@Example.com", "password": "password1"},
    )
    assert first.status_code == 201
    assert first.json()["email"] == "user@example.com"

    second = await client.post(
        "/api/auth/register",
        json={"email": "user@example.com", "password": "password2"},
    )
    assert second.status_code == 409


async def test_login_after_logout(client: AsyncClient) -> None:
    await client.post(
        "/api/auth/register",
        json={"email": "user@example.com", "password": "password1"},
    )
    await client.post("/api/auth/logout")
    response = await client.post(
        "/api/auth/login",
        json={"email": "USER@example.com", "password": "password1"},
    )
    assert response.status_code == 200
    assert response.json()["email"] == "user@example.com"
    me = await client.get("/api/auth/me")
    assert me.status_code == 200


async def test_login_wrong_password(client: AsyncClient) -> None:
    await client.post(
        "/api/auth/register",
        json={"email": "user@example.com", "password": "password1"},
    )
    response = await client.post(
        "/api/auth/login",
        json={"email": "user@example.com", "password": "wrong-password"},
    )
    assert response.status_code == 401


async def test_me_without_cookie(client: AsyncClient) -> None:
    response = await client.get("/api/auth/me")
    assert response.status_code == 401


async def test_logout_invalidates_session(client: AsyncClient) -> None:
    await client.post(
        "/api/auth/register",
        json={"email": "user@example.com", "password": "password1"},
    )
    logout = await client.post("/api/auth/logout")
    assert logout.status_code == 204
    me = await client.get("/api/auth/me")
    assert me.status_code == 401


async def test_health_checks_database(client: AsyncClient) -> None:
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_login_rate_limit_blocks_many_emails_from_one_ip(client: AsyncClient) -> None:
    await client.post(
        "/api/auth/register",
        json={"email": "user@example.com", "password": "password1"},
    )
    for index in range(10):
        failed = await client.post(
            "/api/auth/login",
            json={"email": f"other{index}@example.com", "password": "password1"},
        )
        assert failed.status_code == 401
    blocked = await client.post(
        "/api/auth/login",
        json={"email": "user@example.com", "password": "password1"},
    )
    assert blocked.status_code == 429


async def test_short_password_and_invalid_email_are_rejected(client: AsyncClient) -> None:
    short = await client.post(
        "/api/auth/register",
        json={"email": "user@example.com", "password": "short"},
    )
    assert short.status_code == 422
    invalid = await client.post(
        "/api/auth/register",
        json={"email": "not-an-email", "password": "password1"},
    )
    assert invalid.status_code == 422
    short_login = await client.post(
        "/api/auth/login",
        json={"email": "user@example.com", "password": "short"},
    )
    assert short_login.status_code == 422


async def test_expired_session_is_rejected_and_removed(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    await client.post(
        "/api/auth/register",
        json={"email": "user@example.com", "password": "password1"},
    )
    await db_session.execute(
        update(Session).values(expires_at=datetime.now(UTC) - timedelta(minutes=1))
    )
    await db_session.flush()
    response = await client.get("/api/auth/me")
    assert response.status_code == 401
    remaining = await db_session.scalar(select(func.count()).select_from(Session))
    assert remaining == 0


async def test_me_rejects_unsigned_cookie(client: AsyncClient) -> None:
    client.cookies.set("session_id", "not-a-signed-token")
    response = await client.get("/api/auth/me")
    assert response.status_code == 401


_EXERCISE = {
    "name": "Жим штанги лёжа",
    "primary_muscle": "chest",
    "secondary_muscles": [],
    "equipment": "barbell",
    "weight_type": "standard",
    "weight_unit": "kg",
    "weight_step": 2.5,
    "rep_min": 8,
    "rep_max": 12,
}


async def test_delete_account_requires_login(client: AsyncClient) -> None:
    response = await client.request(
        "DELETE",
        "/api/auth/account",
        json={"password": "password1"},
    )
    assert response.status_code == 401


async def test_delete_account_rejects_wrong_password(client: AsyncClient) -> None:
    await client.post(
        "/api/auth/register",
        json={"email": "user@example.com", "password": "password1"},
    )
    response = await client.request(
        "DELETE",
        "/api/auth/account",
        json={"password": "password2"},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Неверный пароль"
    me = await client.get("/api/auth/me")
    assert me.status_code == 200


async def test_delete_account_removes_user_and_leaves_others(client: AsyncClient) -> None:
    await client.post(
        "/api/auth/register",
        json={"email": "owner@example.com", "password": "password1"},
    )
    exercise = await client.post("/api/exercises", json=_EXERCISE)
    assert exercise.status_code == 201, exercise.text
    workout = await client.post(
        "/api/workouts",
        json={
            "name": "День A",
            "items": [
                {
                    "exercise_id": exercise.json()["id"],
                    "sets": [{"rep_min": 8, "rep_max": 12, "target_rir": 2, "rest_seconds": 120}],
                }
            ],
        },
    )
    assert workout.status_code == 201, workout.text

    await client.post("/api/auth/logout")
    other = await client.post(
        "/api/auth/register",
        json={"email": "other@example.com", "password": "password1"},
    )
    assert other.status_code == 201
    other_exercise = await client.post("/api/exercises", json={**_EXERCISE, "name": "Тяга"})
    assert other_exercise.status_code == 201, other_exercise.text

    await client.post("/api/auth/logout")
    login = await client.post(
        "/api/auth/login",
        json={"email": "owner@example.com", "password": "password1"},
    )
    assert login.status_code == 200
    deleted = await client.request(
        "DELETE",
        "/api/auth/account",
        json={"password": "password1"},
    )
    assert deleted.status_code == 204
    assert "session_id=" in deleted.headers["set-cookie"].lower()
    assert (await client.get("/api/auth/me")).status_code == 401

    # Адрес снова свободен: строка пользователя удалена, а не только сессия.
    again = await client.post(
        "/api/auth/register",
        json={"email": "owner@example.com", "password": "password1"},
    )
    assert again.status_code == 201
    assert (await client.get("/api/exercises")).json() == []
    assert (await client.get("/api/workouts")).json() == []

    await client.post("/api/auth/logout")
    other_login = await client.post(
        "/api/auth/login",
        json={"email": "other@example.com", "password": "password1"},
    )
    assert other_login.status_code == 200
    remaining = await client.get("/api/exercises")
    assert remaining.status_code == 200
    assert [item["name"] for item in remaining.json()] == ["Тяга"]
