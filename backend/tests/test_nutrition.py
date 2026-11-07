from app.models.nutrition import NutritionIntake
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

INTAKE = {"protein_g": 100, "fat_g": 50, "carbs_g": 200}
EMPTY_INTAKE = {"protein_g": None, "fat_g": None, "carbs_g": None, "calories": None}
STUB_TARGET = {
    "available": False,
    "reason": "нет замера InBody",
    "protein_g": None,
    "fat_g": None,
    "carbs_g": None,
    "calories": None,
}


async def _register(client: AsyncClient, email: str) -> None:
    response = await client.post(
        "/api/auth/register",
        json={"email": email, "password": "password1"},
    )
    assert response.status_code == 201


async def _login(client: AsyncClient, email: str) -> None:
    response = await client.post(
        "/api/auth/login",
        json={"email": email, "password": "password1"},
    )
    assert response.status_code == 200


def test_calories_are_not_a_column() -> None:
    assert "calories" not in NutritionIntake.__table__.columns


async def test_nutrition_requires_login(client: AsyncClient) -> None:
    assert (await client.get("/api/nutrition/intake")).status_code == 401
    assert (await client.put("/api/nutrition/intake", json=INTAKE)).status_code == 401
    assert (await client.get("/api/nutrition/targets")).status_code == 401


async def test_get_intake_does_not_create_a_row(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _register(client, "reader@example.com")

    for _ in range(2):
        response = await client.get("/api/nutrition/intake")
        assert response.status_code == 200
        assert response.json() == EMPTY_INTAKE

    rows = await db_session.scalar(select(func.count()).select_from(NutritionIntake))
    assert rows == 0


async def test_owner_saves_grams_and_receives_calculated_calories(client: AsyncClient) -> None:
    await _register(client, "owner@example.com")

    saved = await client.put("/api/nutrition/intake", json=INTAKE)
    assert saved.status_code == 200
    assert saved.json() == {**INTAKE, "calories": 1650}

    again = await client.get("/api/nutrition/intake")
    assert again.status_code == 200
    assert again.json() == {**INTAKE, "calories": 1650}

    replaced = await client.put(
        "/api/nutrition/intake",
        json={"protein_g": 120, "fat_g": 40, "carbs_g": 180},
    )
    assert replaced.status_code == 200
    # 120×4 + 180×4 + 40×9 = 480 + 720 + 360.
    assert replaced.json()["calories"] == 1560
    assert replaced.json()["protein_g"] == 120


async def test_other_user_does_not_see_the_owner_intake(client: AsyncClient) -> None:
    await _register(client, "owner@example.com")
    await client.put("/api/nutrition/intake", json=INTAKE)
    await client.post("/api/auth/logout")

    await _register(client, "other@example.com")
    hidden = await client.get("/api/nutrition/intake")
    assert hidden.status_code == 200
    assert hidden.json() == EMPTY_INTAKE

    await client.post("/api/auth/logout")
    await _login(client, "owner@example.com")
    own = await client.get("/api/nutrition/intake")
    assert own.status_code == 200
    assert own.json() == {**INTAKE, "calories": 1650}


async def test_put_rejects_invalid_grams(client: AsyncClient) -> None:
    await _register(client, "owner@example.com")
    await client.put("/api/nutrition/intake", json=INTAKE)

    for body in (
        {"fat_g": 50, "carbs_g": 200},
        {"protein_g": -1, "fat_g": 50, "carbs_g": 200},
        {"protein_g": 2001, "fat_g": 50, "carbs_g": 200},
    ):
        response = await client.put("/api/nutrition/intake", json=body)
        assert response.status_code == 422, body

    kept = await client.get("/api/nutrition/intake")
    assert kept.json() == {**INTAKE, "calories": 1650}


PROFILE = {
    "goal": "maintenance",
    "height_cm": 180,
    "age": 32,
    "sex": "male",
    "weight_unit": "kg",
    "theme": "light",
}

SCAN = {
    "measured_on": "2026-10-26",
    "weight_kg": 80,
    "smm_kg": 40,
    "bfm_kg": 16,
    "pbf_percent": 20,
    "tbw_l": 48,
    "visceral_fat_level": 4,
    "bmr_kcal": 1700,
}


async def test_macro_target_stays_empty_without_a_scan(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _register(client, "owner@example.com")
    await client.put("/api/nutrition/intake", json=INTAKE)
    before = await db_session.scalar(select(func.count()).select_from(NutritionIntake))

    response = await client.get("/api/nutrition/targets")
    assert response.status_code == 200
    assert response.json() == STUB_TARGET

    after = await db_session.scalar(select(func.count()).select_from(NutritionIntake))
    assert after == before == 1


async def test_macro_target_without_a_goal_explains_why(client: AsyncClient) -> None:
    await _register(client, "owner@example.com")
    created = await client.post("/api/inbody", json=SCAN)
    assert created.status_code == 201, created.text

    response = await client.get("/api/nutrition/targets")
    assert response.status_code == 200
    assert response.json()["available"] is False
    assert response.json()["reason"] == "не выбрана цель"
    assert response.json()["calories"] is None


async def test_macro_target_uses_the_latest_scan_and_profile_goal(client: AsyncClient) -> None:
    await _register(client, "owner@example.com")
    saved = await client.put("/api/profile", json=PROFILE)
    assert saved.status_code == 200, saved.text
    created = await client.post("/api/inbody", json=SCAN)
    assert created.status_code == 201, created.text
    earlier = {**SCAN, "measured_on": "2026-10-01", "weight_kg": 70, "pbf_percent": 18}
    assert (await client.post("/api/inbody", json=earlier)).status_code == 201

    response = await client.get("/api/nutrition/targets")
    assert response.status_code == 200
    # Последний по дате замер — 80 кг и 20% жира. Числа совпадают с test_nutrition_logic.
    assert response.json() == {
        "available": True,
        "reason": None,
        "protein_g": 128,
        "fat_g": 80,
        "carbs_g": 349.3,
        "calories": 2629,
    }

    await client.post("/api/auth/logout")
    await _register(client, "other@example.com")
    hidden = await client.get("/api/nutrition/targets")
    assert hidden.status_code == 200
    assert hidden.json() == STUB_TARGET
