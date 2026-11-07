from httpx import AsyncClient
from tests.test_log import _exercise, _plan_workout, _register, _start


async def test_today_requires_login(client: AsyncClient) -> None:
    response = await client.get("/api/today", params={"day": "2026-11-07"})
    assert response.status_code == 401


async def test_today_log_state_follows_the_workout(client: AsyncClient) -> None:
    await _register(client)
    exercise_id = await _exercise(client)
    planned = await _plan_workout(client, exercise_id, "2026-11-07")

    empty = await client.get("/api/today", params={"day": "2026-11-06"})
    assert empty.status_code == 200, empty.text
    assert empty.json() == {"date": "2026-11-06", "entries": [], "export_reminder": False}

    fresh = await client.get("/api/today", params={"day": "2026-11-07"})
    assert fresh.status_code == 200, fresh.text
    [entry] = fresh.json()["entries"]
    assert entry["id"] == planned["id"]
    assert entry["name"] == "День A"
    assert entry["log_state"] == "none"

    started_status, started = await _start(client, planned["id"])
    assert started_status == 201
    opened = await client.get("/api/today", params={"day": "2026-11-07"})
    assert opened.json()["entries"][0]["log_state"] == "open"

    finished = await client.post(f"/api/performed/{started['id']}/finish")
    assert finished.status_code == 200, finished.text
    closed = await client.get("/api/today", params={"day": "2026-11-07"})
    assert closed.json()["entries"][0]["log_state"] == "finished"
    assert closed.json()["entries"][0]["status"] == "done"


async def test_today_rest_day_has_no_log(client: AsyncClient) -> None:
    await _register(client)
    created = await client.post("/api/plan/entries", json={"date": "2026-11-08", "kind": "rest"})
    assert created.status_code == 201, created.text

    response = await client.get("/api/today", params={"day": "2026-11-08"})
    assert response.status_code == 200, response.text
    [entry] = response.json()["entries"]
    assert entry["kind"] == "rest"
    assert entry["status"] is None
    assert entry["log_state"] == "none"


async def test_today_hides_another_users_plan(client: AsyncClient) -> None:
    await _register(client, "owner@example.com")
    exercise_id = await _exercise(client)
    await _plan_workout(client, exercise_id, "2026-11-07")
    logout = await client.post("/api/auth/logout")
    assert logout.status_code == 204

    await _register(client, "other@example.com")
    response = await client.get("/api/today", params={"day": "2026-11-07"})
    assert response.status_code == 200, response.text
    assert response.json()["entries"] == []
