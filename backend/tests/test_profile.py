from app.models.profile import Profile as ProfileModel
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

FULL_PROFILE = {
    "goal": "recomposition",
    "height_cm": 180,
    "age": 32,
    "sex": "male",
    "weight_unit": "kg",
    "theme": "dark",
}


async def _register(client: AsyncClient, email: str) -> None:
    response = await client.post(
        "/api/auth/register",
        json={"email": email, "password": "password1"},
    )
    assert response.status_code == 201


async def test_profile_requires_login(client: AsyncClient) -> None:
    response = await client.get("/api/profile")
    assert response.status_code == 401

    response = await client.put("/api/profile", json=FULL_PROFILE)
    assert response.status_code == 401


async def test_new_user_gets_default_profile(client: AsyncClient) -> None:
    await _register(client, "user@example.com")

    response = await client.get("/api/profile")
    assert response.status_code == 200
    assert response.json() == {
        "goal": None,
        "height_cm": None,
        "age": None,
        "sex": None,
        "weight_unit": "kg",
        "theme": "system",
    }


async def test_put_replaces_profile(client: AsyncClient) -> None:
    await _register(client, "user@example.com")

    response = await client.put("/api/profile", json=FULL_PROFILE)
    assert response.status_code == 200
    assert response.json() == FULL_PROFILE

    response = await client.get("/api/profile")
    assert response.json() == FULL_PROFILE

    cleared = {**FULL_PROFILE, "goal": None, "height_cm": None, "sex": None}
    response = await client.put("/api/profile", json=cleared)
    assert response.status_code == 200
    assert response.json() == cleared


async def test_put_accepts_lb_and_light_theme(client: AsyncClient) -> None:
    await _register(client, "user@example.com")

    body = {**FULL_PROFILE, "weight_unit": "lb", "theme": "light"}
    response = await client.put("/api/profile", json=body)
    assert response.status_code == 200
    assert response.json()["weight_unit"] == "lb"
    assert response.json()["theme"] == "light"


async def test_put_rejects_partial_body(client: AsyncClient) -> None:
    await _register(client, "user@example.com")
    await client.put("/api/profile", json=FULL_PROFILE)

    # Без обязательных полей запрос отклоняется, а не стирает сохранённые данные.
    response = await client.put("/api/profile", json={"theme": "light"})
    assert response.status_code == 422

    response = await client.get("/api/profile")
    assert response.json() == FULL_PROFILE


async def test_put_rejects_invalid_values(client: AsyncClient) -> None:
    await _register(client, "user@example.com")

    invalid_bodies = [
        {**FULL_PROFILE, "goal": "bulk"},
        {**FULL_PROFILE, "sex": "unknown"},
        {**FULL_PROFILE, "weight_unit": "stone"},
        {**FULL_PROFILE, "theme": "blue"},
        {**FULL_PROFILE, "height_cm": 99},
        {**FULL_PROFILE, "height_cm": 251},
        {**FULL_PROFILE, "age": 9},
        {**FULL_PROFILE, "age": 121},
    ]
    for body in invalid_bodies:
        response = await client.put("/api/profile", json=body)
        assert response.status_code == 422, body


async def test_profiles_are_isolated_between_users(client: AsyncClient) -> None:
    await _register(client, "first@example.com")
    await client.put("/api/profile", json=FULL_PROFILE)
    await client.post("/api/auth/logout")

    await _register(client, "second@example.com")
    response = await client.get("/api/profile")
    assert response.status_code == 200
    assert response.json()["goal"] is None
    assert response.json()["theme"] == "system"


async def test_get_profile_does_not_write(client: AsyncClient, db_session: AsyncSession) -> None:
    await _register(client, "reader@example.com")

    for _ in range(2):
        response = await client.get("/api/profile")
        assert response.status_code == 200

    rows = await db_session.scalar(select(func.count()).select_from(ProfileModel))
    assert rows == 0

    response = await client.put("/api/profile", json=FULL_PROFILE)
    assert response.status_code == 200
    rows = await db_session.scalar(select(func.count()).select_from(ProfileModel))
    assert rows == 1
