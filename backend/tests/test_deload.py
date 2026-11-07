"""API разгрузки: неделя по умолчанию, предложение без записи и принятие отдельно."""

import datetime as dt
from typing import Any

from app.models.plan import PlannedWorkout
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from tests.test_log import _start, _values

BENCH = {
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


async def _register(client: AsyncClient, email: str) -> None:
    response = await client.post(
        "/api/auth/register", json={"email": email, "password": "password1"}
    )
    assert response.status_code == 201


def _week(
    week_type: str = "hypertrophy",
    rep_min: int = 8,
    rep_max: int = 12,
    rir: int = 2,
    volume: float = 1.0,
) -> dict[str, Any]:
    return {
        "week_type": week_type,
        "rep_min": rep_min,
        "rep_max": rep_max,
        "target_rir": rir,
        "volume_multiplier": volume,
    }


async def _template(client: AsyncClient) -> str:
    first = await client.post("/api/exercises", json=BENCH)
    assert first.status_code == 201, first.text
    second = await client.post(
        "/api/exercises",
        json={**BENCH, "name": "Тяга штанги", "primary_muscle": "back"},
    )
    assert second.status_code == 201, second.text
    sets = [
        {"rep_min": 8, "rep_max": 12, "target_rir": 2, "rest_seconds": 90},
        {"rep_min": 8, "rep_max": 12, "target_rir": 2, "rest_seconds": 90},
    ]
    created = await client.post(
        "/api/workouts",
        json={
            "name": "День A",
            "items": [
                {"exercise_id": first.json()["id"], "sets": sets},
                {"exercise_id": second.json()["id"], "sets": sets},
            ],
        },
    )
    assert created.status_code == 201, created.text
    return created.json()["id"]


async def _create(client: AsyncClient, template_id: str, weeks: list[dict[str, Any]]) -> dict:
    response = await client.post(
        "/api/blocks",
        json={
            "name": "Блок",
            "weeks": weeks,
            "schedule": [{"day_index": 0, "kind": "workout", "template_id": template_id}],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _plan(client: AsyncClient, start: dt.date, end: dt.date) -> list[dict]:
    response = await client.get(
        "/api/plan", params={"start": start.isoformat(), "end": end.isoformat()}
    )
    assert response.status_code == 200, response.text
    return response.json()


def _on(entries: list[dict], day: dt.date) -> dict:
    [entry] = [entry for entry in entries if entry["date"] == day.isoformat()]
    return entry


async def _finish(client: AsyncClient, planned_id: str, reps: int, rir: int) -> None:
    _, workout = await _start(client, planned_id)
    for item in workout["items"]:
        for logged in item["sets"]:
            saved = await client.put(
                f"/api/performed/{workout['id']}/sets/{logged['id']}",
                json=_values(weight=100, reps=reps, rir=rir),
            )
            assert saved.status_code == 200, saved.text
    finished = await client.post(f"/api/performed/{workout['id']}/finish")
    assert finished.status_code == 200, finished.text


async def _rows(db: AsyncSession) -> int:
    return int(await db.scalar(select(func.count()).select_from(PlannedWorkout)) or 0)


async def test_deload_suggestion_requires_login(client: AsyncClient) -> None:
    placement_id = "11111111-1111-4111-8111-111111111111"
    suggestion = await client.get(f"/api/blocks/placements/{placement_id}/deload-suggestion")
    accept = await client.post(f"/api/blocks/placements/{placement_id}/deload-suggestion/accept")
    assert suggestion.status_code == accept.status_code == 401


async def test_create_adds_default_deload_and_keeps_a_custom_one(client: AsyncClient) -> None:
    await _register(client, "default@example.com")
    template_id = await _template(client)

    created = await _create(client, template_id, [_week("strength", rep_min=3, rep_max=5, rir=1)])
    assert created["length_weeks"] == 2
    assert created["weeks"][1] == {
        "position": 2,
        "week_type": "deload",
        "rep_min": 3,
        "rep_max": 5,
        "target_rir": 4,
        "volume_multiplier": 0.5,
    }

    custom = await _create(
        client,
        template_id,
        [_week(), _week("deload", rir=3, volume=0.6)],
    )
    assert custom["length_weeks"] == 2
    assert custom["weeks"][1]["volume_multiplier"] == 0.6
    assert custom["weeks"][1]["target_rir"] == 3

    replaced = await client.put(
        f"/api/blocks/{custom['id']}",
        json={
            "name": "Блок",
            "weeks": [_week(), _week("deload", rir=3, volume=0.5)],
            "schedule": [{"day_index": 0, "kind": "workout", "template_id": template_id}],
        },
    )
    assert replaced.status_code == 200, replaced.text
    assert replaced.json()["weeks"][1]["volume_multiplier"] == 0.5
    assert replaced.json()["weeks"][1]["target_rir"] == 3


async def test_twelve_weeks_without_deload_are_rejected(client: AsyncClient) -> None:
    await _register(client, "full@example.com")
    template_id = await _template(client)
    response = await client.post(
        "/api/blocks",
        json={
            "name": "Длинный",
            "weeks": [_week() for _ in range(12)],
            "schedule": [{"day_index": 0, "kind": "workout", "template_id": template_id}],
        },
    )
    assert response.status_code == 422
    assert "12" in response.json()["detail"]


async def test_other_users_placement_is_not_found(client: AsyncClient) -> None:
    await _register(client, "owner@example.com")
    template_id = await _template(client)
    block = await _create(client, template_id, [_week(), _week("deload")])
    applied = await client.post(
        f"/api/blocks/{block['id']}/apply", json={"start_date": "2026-11-02"}
    )
    assert applied.status_code == 201, applied.text
    placement_id = applied.json()["id"]
    await client.post("/api/auth/logout")
    await _register(client, "other@example.com")

    suggestion = await client.get(f"/api/blocks/placements/{placement_id}/deload-suggestion")
    accept = await client.post(f"/api/blocks/placements/{placement_id}/deload-suggestion/accept")
    assert suggestion.status_code == accept.status_code == 404
    assert suggestion.json()["detail"] == "Блок в календаре не найден"


async def test_suggestion_does_not_write_and_accept_turns_the_current_week_into_deload(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _register(client, "tired@example.com")
    template_id = await _template(client)
    block = await _create(
        client,
        template_id,
        [_week(), _week(), _week(), _week("deload", volume=0.5, rir=4)],
    )
    today = dt.date.today()
    start = today - dt.timedelta(days=14)
    applied = await client.post(
        f"/api/blocks/{block['id']}/apply", json={"start_date": start.isoformat()}
    )
    assert applied.status_code == 201, applied.text
    placement_id = applied.json()["id"]
    end = dt.date.fromisoformat(applied.json()["end_date"])

    quiet = await client.get(f"/api/blocks/placements/{placement_id}/deload-suggestion")
    assert quiet.status_code == 200, quiet.text
    assert quiet.json()["suggest"] is False
    assert quiet.json()["reasons"] == []
    before = await _plan(client, start, end)
    db_session.expire_all()
    rows_before = await _rows(db_session)
    again = await client.get(f"/api/blocks/placements/{placement_id}/deload-suggestion")
    assert again.json() == quiet.json()
    assert await _plan(client, start, end) == before
    db_session.expire_all()
    assert await _rows(db_session) == rows_before

    refused = await client.post(f"/api/blocks/placements/{placement_id}/deload-suggestion/accept")
    assert refused.status_code == 422
    assert await _plan(client, start, end) == before

    first = _on(before, start)
    second = _on(before, start + dt.timedelta(days=7))
    await _finish(client, first["id"], reps=10, rir=3)
    await _finish(client, second["id"], reps=8, rir=0)

    suggestion = await client.get(f"/api/blocks/placements/{placement_id}/deload-suggestion")
    assert suggestion.status_code == 200, suggestion.text
    body = suggestion.json()
    assert body["suggest"] is True
    assert body["week_position"] == 3
    assert {item["code"] for item in body["reasons"]} == {"low_rir", "rep_drop"}

    logged = await _plan(client, start, end)
    accepted = await client.post(f"/api/blocks/placements/{placement_id}/deload-suggestion/accept")
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["week_position"] == 3
    assert accepted.json()["volume_multiplier"] == 0.5
    assert accepted.json()["target_rir"] == 4

    updated = await _plan(client, start, end)
    done = _on(updated, start)
    assert done["items"][0]["sets"][0]["target_rir"] == 2
    assert len(done["items"][0]["sets"]) == 2
    current = _on(updated, today)
    assert len(current["items"][0]["sets"]) == 1
    assert current["items"][0]["sets"][0]["target_rir"] == 4
    assert current["items"][0]["sets"][0]["rep_min"] == 8
    assert _on(logged, start)["items"] == done["items"]

    hidden = await client.get(f"/api/blocks/placements/{placement_id}/deload-suggestion")
    assert hidden.json()["suggest"] is False
    assert hidden.json()["message"] == "Эта неделя уже разгрузочная."
    repeated = await client.post(f"/api/blocks/placements/{placement_id}/deload-suggestion/accept")
    assert repeated.status_code == 422
