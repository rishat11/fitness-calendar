import uuid

from app.models.plan import PlannedWorkout
from app.models.workout import WorkoutTemplate
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from tests.test_log import _exercise, _plan_workout, _register, _start, _values


async def _counts(db: AsyncSession, user_id: uuid.UUID) -> tuple[int, int]:
    planned = await db.scalar(
        select(func.count()).select_from(PlannedWorkout).where(PlannedWorkout.user_id == user_id)
    )
    templates = await db.scalar(
        select(func.count()).select_from(WorkoutTemplate).where(WorkoutTemplate.user_id == user_id)
    )
    return int(planned or 0), int(templates or 0)


async def test_progression_requires_login(client: AsyncClient) -> None:
    exercise_id = uuid.uuid4()
    assert (await client.get(f"/api/progression/{exercise_id}")).status_code == 401
    denied = await client.post(
        f"/api/progression/{exercise_id}/decision", json={"action": "reject"}
    )
    assert denied.status_code == 401


async def test_other_users_exercise_is_not_found(client: AsyncClient) -> None:
    await _register(client, "owner@example.com")
    exercise_id = await _exercise(client)
    await client.post("/api/auth/logout")
    await _register(client, "other@example.com")

    missing = await client.get(f"/api/progression/{exercise_id}")
    assert missing.status_code == 404
    denied = await client.post(
        f"/api/progression/{exercise_id}/decision", json={"action": "accept"}
    )
    assert denied.status_code == 404


async def test_accept_fills_the_open_set_and_does_not_write_plan_or_template(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _register(client)
    exercise_id = await _exercise(client)
    planned = await _plan_workout(client, exercise_id, "2026-11-10")
    _, workout = await _start(client, planned["id"])
    for logged in workout["items"][0]["sets"]:
        saved = await client.put(
            f"/api/performed/{workout['id']}/sets/{logged['id']}",
            json=_values(weight=100, reps=12, rir=2),
        )
        assert saved.status_code == 200, saved.text
    finished = await client.post(f"/api/performed/{workout['id']}/finish")
    assert finished.status_code == 200, finished.text

    hint = await client.get(f"/api/progression/{exercise_id}")
    assert hint.status_code == 200, hint.text
    assert hint.json()["status"] == "increase_weight"
    assert hint.json()["suggested_weight"] == 102.5

    second = await _plan_workout(client, exercise_id, "2026-11-17")
    _, open_log = await _start(client, second["id"])
    me = await client.get("/api/auth/me")
    user_id = uuid.UUID(me.json()["id"])
    db_session.expire_all()
    before = await _counts(db_session, user_id)
    templates = await client.get("/api/workouts")
    plan = await client.get("/api/plan", params={"start": "2026-11-01", "end": "2026-12-31"})
    assert templates.status_code == plan.status_code == 200

    accepted = await client.post(
        f"/api/progression/{exercise_id}/decision",
        json={"action": "accept", "performed_id": open_log["id"]},
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["set_id"] == open_log["items"][0]["sets"][0]["id"]
    assert accepted.json()["weight"] == 102.5

    db_session.expire_all()
    assert await _counts(db_session, user_id) == before
    assert (await client.get("/api/workouts")).json() == templates.json()
    plan_again = await client.get("/api/plan", params={"start": "2026-11-01", "end": "2026-12-31"})
    assert plan_again.json() == plan.json()

    hidden = await client.get(f"/api/progression/{exercise_id}")
    assert hidden.status_code == 200
    assert hidden.json() is None

    _, again = await _start(client, second["id"])
    assert again["items"][0]["sets"][0]["weight"] == 102.5
    assert again["items"][0]["sets"][1]["weight"] is None


async def test_new_session_shows_the_hint_again(client: AsyncClient) -> None:
    await _register(client, "again@example.com")
    exercise_id = await _exercise(client)
    first = await _plan_workout(client, exercise_id, "2026-11-10")
    _, workout = await _start(client, first["id"])
    logged = workout["items"][0]["sets"][0]
    saved = await client.put(
        f"/api/performed/{workout['id']}/sets/{logged['id']}",
        json=_values(weight=100, reps=12, rir=2),
    )
    assert saved.status_code == 200, saved.text
    assert (await client.post(f"/api/performed/{workout['id']}/finish")).status_code == 200

    rejected = await client.post(
        f"/api/progression/{exercise_id}/decision", json={"action": "reject"}
    )
    assert rejected.status_code == 200, rejected.text
    assert (await client.get(f"/api/progression/{exercise_id}")).json() is None

    second = await _plan_workout(client, exercise_id, "2026-11-17")
    _, next_workout = await _start(client, second["id"])
    logged = next_workout["items"][0]["sets"][0]
    saved = await client.put(
        f"/api/performed/{next_workout['id']}/sets/{logged['id']}",
        json=_values(weight=102.5, reps=12, rir=2),
    )
    assert saved.status_code == 200, saved.text
    assert (await client.post(f"/api/performed/{next_workout['id']}/finish")).status_code == 200

    hint = await client.get(f"/api/progression/{exercise_id}")
    assert hint.status_code == 200, hint.text
    body = hint.json()
    assert body["status"] == "increase_weight"
    assert body["suggested_weight"] == 105
    assert body["last_session_id"] == next_workout["id"]
