import uuid

from app.models.log import PerformedItem
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from tests.test_log import ASSISTED, _exercise, _plan_workout, _register, _start, _values

CABLE = {
    "name": "Тяга блока",
    "primary_muscle": "back",
    "secondary_muscles": [],
    "equipment": "cable",
    "weight_type": "stack_plus_extra",
    "weight_unit": "kg",
    "weight_step": 2.5,
    "rep_min": 8,
    "rep_max": 12,
}

ROW = {
    **CABLE,
    "name": "Тяга гантели",
    "equipment": "dumbbell",
    "weight_type": "standard",
}


async def _finish_with(
    client: AsyncClient, exercise_id: str, day: str, sets: list[dict], note: str | None = None
) -> dict:
    planned = await _plan_workout(client, exercise_id, day)
    _, workout = await _start(client, planned["id"])
    item = workout["items"][0]
    if note is not None:
        noted = await client.patch(
            f"/api/performed/{workout['id']}/items/{item['id']}",
            json={"note": note},
        )
        assert noted.status_code == 200, noted.text
    for logged, body in zip(item["sets"], sets, strict=False):
        saved = await client.put(
            f"/api/performed/{workout['id']}/sets/{logged['id']}",
            json=_values(**body),
        )
        assert saved.status_code == 200, saved.text
    for body in sets[len(item["sets"]) :]:
        created = await client.post(
            f"/api/performed/{workout['id']}/items/{item['id']}/sets",
            json=body,
        )
        assert created.status_code == 201, created.text
    finished = await client.post(f"/api/performed/{workout['id']}/finish")
    assert finished.status_code == 200, finished.text
    return finished.json()


async def test_history_requires_login(client: AsyncClient) -> None:
    response = await client.get(f"/api/exercises/{uuid.uuid4()}/history")
    assert response.status_code == 401


async def test_other_users_history_is_not_found(client: AsyncClient) -> None:
    await _register(client, "owner-history@example.com")
    exercise_id = await _exercise(client, CABLE)
    await _finish_with(client, exercise_id, "2026-11-01", [{"weight": 40, "reps": 8}])
    await client.post("/api/auth/logout")
    await _register(client, "other-history@example.com")

    missing = await client.get(f"/api/exercises/{exercise_id}/history")
    assert missing.status_code == 404
    assert missing.json()["detail"] == "Упражнение не найдено"
    unknown = await client.get(f"/api/exercises/{uuid.uuid4()}/history")
    assert unknown.status_code == 404


async def test_history_uses_snapshot_and_skips_non_working_sets(client: AsyncClient) -> None:
    await _register(client, "history@example.com")
    exercise_id = await _exercise(client, CABLE)
    await _finish_with(
        client,
        exercise_id,
        "2026-11-01",
        [{"weight": 40, "extra_weight": 0, "reps": 6, "rir": 3}],
        note="старая заметка",
    )
    latest = await _finish_with(
        client,
        exercise_id,
        "2026-11-08",
        [
            {"weight": 30, "reps": 15, "is_warmup": True},
            {"weight": 80, "reps": 12, "is_assisted": True},
            {"weight": 90, "reps": 3, "is_negative": True},
            {"weight": 70, "reps": None},
            {"weight": 50, "extra_weight": 2.5, "reps": 8, "rir": 2},
        ],
        note="рукоять узкая",
    )

    open_day = await _plan_workout(client, exercise_id, "2026-11-15")
    _, open_log = await _start(client, open_day["id"])
    saved = await client.put(
        f"/api/performed/{open_log['id']}/sets/{open_log['items'][0]['sets'][0]['id']}",
        json=_values(weight=999, reps=1),
    )
    assert saved.status_code == 200, saved.text

    edited = await client.put(
        f"/api/exercises/{exercise_id}",
        json={**CABLE, "name": "Тяга блока сидя", "weight_type": "stack", "weight_step": 5},
    )
    assert edited.status_code == 200, edited.text

    history = await client.get(f"/api/exercises/{exercise_id}/history")
    assert history.status_code == 200, history.text
    body = history.json()
    assert [session["date"] for session in body["sessions"]] == ["2026-11-08", "2026-11-01"]
    assert body["sessions"][0]["notes"] == ["рукоять узкая"]
    assert body["sessions"][1]["notes"] == ["старая заметка"]
    weights = [logged["weight"] for session in body["sessions"] for logged in session["sets"]]
    assert 999 not in weights
    assert 50 in weights
    working = next(logged for logged in body["sessions"][0]["sets"] if logged["weight"] == 50)
    assert working["extra_weight"] == 2.5
    assert working["reps"] == 8
    assert working["rir"] == 2
    assert working["is_warmup"] is False
    warmup = next(logged for logged in body["sessions"][0]["sets"] if logged["is_warmup"])
    assert warmup["weight"] == 30
    # Снимок был «стопка + доп. вес»: 50 + 2,5. Справочник уже «только стопка», но нагрузка прежняя.
    assert body["sessions"][0]["best"]["load"] == 52.5
    assert body["sessions"][0]["best"]["reps"] == 8
    assert body["sessions"][0]["best"]["epley_1rm"] == 66.5
    assert body["sessions"][1]["best"]["load"] == 40
    assert body["sessions"][1]["best"]["epley_1rm"] == 48

    catalog = await client.get(f"/api/exercises/{exercise_id}")
    assert catalog.json()["name"] == "Тяга блока сидя"
    assert catalog.json()["weight_type"] == "stack"
    assert catalog.json()["weight_step"] == 5
    _, again = await _start(client, latest["planned_id"])
    assert again["items"][0]["weight_type"] == "stack_plus_extra"
    assert again["items"][0]["weight_step"] == 2.5
    stored = next(row for row in again["items"][0]["sets"] if row["weight"] == 50)
    assert stored["extra_weight"] == 2.5


async def test_deleted_exercise_is_absent(client: AsyncClient, db_session: AsyncSession) -> None:
    await _register(client, "deleted-history@example.com")
    kept_id = await _exercise(client, CABLE)
    removed_id = await _exercise(client, ROW)
    planned = await _plan_workout(client, kept_id, "2026-11-03")
    _, workout = await _start(client, planned["id"])
    added = await client.post(
        f"/api/performed/{workout['id']}/items",
        json={"exercise_id": removed_id},
    )
    assert added.status_code == 201, added.text
    side = added.json()["items"][1]
    noted = await client.patch(
        f"/api/performed/{workout['id']}/items/{side['id']}",
        json={"note": "заметка удалённого"},
    )
    assert noted.status_code == 200, noted.text
    saved = await client.put(
        f"/api/performed/{workout['id']}/sets/{side['sets'][0]['id']}",
        json=_values(weight=77, reps=5),
    )
    assert saved.status_code == 200, saved.text
    await client.put(
        f"/api/performed/{workout['id']}/sets/{workout['items'][0]['sets'][0]['id']}",
        json=_values(weight=40, extra_weight=5, reps=8),
    )
    assert (await client.post(f"/api/performed/{workout['id']}/finish")).status_code == 200

    removed = await client.delete(f"/api/exercises/{removed_id}")
    assert removed.status_code == 204, removed.text

    gone = await client.get(f"/api/exercises/{removed_id}/history")
    assert gone.status_code == 404

    history = await client.get(f"/api/exercises/{kept_id}/history")
    assert history.status_code == 200, history.text
    body = history.json()
    notes = [note for session in body["sessions"] for note in session["notes"]]
    weights = [logged["weight"] for session in body["sessions"] for logged in session["sets"]]
    assert "заметка удалённого" not in notes
    assert 77 not in weights
    assert weights == [40]

    db_session.expire_all()
    item = await db_session.scalar(
        select(PerformedItem)
        .where(PerformedItem.id == uuid.UUID(side["id"]))
        .options(selectinload(PerformedItem.sets))
    )
    assert item is not None
    assert item.exercise_id is None
    assert item.sets[0].exercise_id is None
    assert item.sets[0].weight == 77
    assert item.note == "заметка удалённого"


async def test_assisted_best_has_no_epley(client: AsyncClient) -> None:
    await _register(client, "assisted-history@example.com")
    exercise_id = await _exercise(client, ASSISTED)
    await _finish_with(
        client,
        exercise_id,
        "2026-11-02",
        [{"weight": 40, "reps": 10, "rir": 3}, {"weight": 30, "reps": 12}],
    )

    history = await client.get(f"/api/exercises/{exercise_id}/history")
    assert history.status_code == 200, history.text
    best = history.json()["sessions"][0]["best"]
    assert best["load"] is None
    assert best["epley_1rm"] is None
    assert best["reps"] == 12


async def test_empty_history(client: AsyncClient) -> None:
    await _register(client, "empty-history@example.com")
    exercise_id = await _exercise(client, CABLE)

    history = await client.get(f"/api/exercises/{exercise_id}/history")
    assert history.status_code == 200, history.text
    assert history.json() == {"sessions": []}
