from httpx import AsyncClient
from tests.test_inbody import SCAN, _register

INTAKE = {"protein_g": 100, "fat_g": 70, "carbs_g": 250}


async def test_recommendations_require_login(client: AsyncClient) -> None:
    assert (await client.get("/api/recommendations")).status_code == 401


async def test_other_users_scans_do_not_enter_the_result(client: AsyncClient) -> None:
    await _register(client, "owner@example.com")
    assert (await client.put("/api/nutrition/intake", json=INTAKE)).status_code == 200
    assert (await client.post("/api/inbody", json=SCAN)).status_code == 201
    own = await client.get("/api/recommendations")
    assert own.status_code == 200, own.text
    own_body = own.json()
    assert own_body["disclaimer"]
    assert "84.7" in str(own_body["items"])

    await client.post("/api/auth/logout")
    await _register(client, "other@example.com")
    foreign = await client.get("/api/recommendations")
    assert foreign.status_code == 200, foreign.text
    assert "84.7" not in str(foreign.json())
    assert any(item["code"] == "insufficient_scans" for item in foreign.json()["items"])
