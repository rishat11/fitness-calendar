from app.services.plan_shift import HISTORY_LIMIT
from httpx import AsyncClient

BENCH_BODY = {
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
        "/api/auth/register",
        json={"email": email, "password": "password1"},
    )
    assert response.status_code == 201


async def _template(client: AsyncClient, name: str) -> str:
    exercise = await client.post("/api/exercises", json=BENCH_BODY)
    assert exercise.status_code == 201, exercise.text
    created = await client.post(
        "/api/workouts",
        json={
            "name": name,
            "items": [
                {
                    "exercise_id": exercise.json()["id"],
                    "sets": [{"rep_min": 8, "rep_max": 12, "target_rir": 2, "rest_seconds": 90}],
                }
            ],
        },
    )
    assert created.status_code == 201, created.text
    return created.json()["id"]


async def _add(
    client: AsyncClient,
    day: str,
    *,
    template_id: str | None = None,
    kind: str = "workout",
    name: str | None = None,
) -> dict:
    body: dict = {"date": day, "kind": kind}
    if kind == "workout":
        if template_id is not None:
            body["template_id"] = template_id
        else:
            body["name"] = name or "Тренировка"
    response = await client.post("/api/plan/entries", json=body)
    assert response.status_code == 201, response.text
    return response.json()


async def _dates(client: AsyncClient) -> dict[str, str]:
    response = await client.get("/api/plan", params={"start": "2026-11-01", "end": "2026-11-30"})
    assert response.status_code == 200, response.text
    return {entry["id"]: entry["date"] for entry in response.json()}


def _by_date(entries: list[dict]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}
    for entry in entries:
        grouped.setdefault(entry["date"], []).append(entry)
    return grouped


async def test_shift_endpoints_require_login(client: AsyncClient) -> None:
    body = {
        "operation": "shift_only",
        "entry_id": "00000000-0000-0000-0000-000000000001",
        "days": 1,
    }
    assert (await client.post("/api/plan/shift/preview", json=body)).status_code == 401
    assert (await client.post("/api/plan/shift/apply", json=body)).status_code == 401
    assert (await client.post("/api/plan/shift/undo")).status_code == 401
    assert (await client.get("/api/plan/shift/history")).status_code == 401


async def test_preview_matches_apply_and_leaves_done_and_skipped(client: AsyncClient) -> None:
    await _register(client, "user@example.com")
    template_id = await _template(client, "День A")
    monday = await _add(client, "2026-11-02", template_id=template_id)
    rest = await _add(client, "2026-11-03", kind="rest")
    done = await _add(client, "2026-11-04", name="Сделана")
    later = await _add(client, "2026-11-05", name="Позже")
    skipped = await _add(client, "2026-11-06", name="Пропуск")
    assert (
        await client.patch(f"/api/plan/{done['id']}", json={"status": "done"})
    ).status_code == 200
    assert (
        await client.patch(f"/api/plan/{skipped['id']}", json={"status": "skipped"})
    ).status_code == 200

    body = {
        "operation": "shift_following",
        "entry_id": monday["id"],
        "days": 1,
        "resolution": "cascade",
    }
    preview = await client.post("/api/plan/shift/preview", json=body)
    assert preview.status_code == 200, preview.text
    assert (await _dates(client))[monday["id"]] == "2026-11-02"

    applied = await client.post("/api/plan/shift/apply", json=body)
    assert applied.status_code == 200, applied.text
    assert applied.json()["applied"] is True
    assert applied.json()["changes"] == preview.json()["changes"]

    dates = await _dates(client)
    assert dates[monday["id"]] == "2026-11-03"
    assert dates[rest["id"]] == "2026-11-05"
    assert dates[done["id"]] == "2026-11-04"
    assert dates[later["id"]] == "2026-11-07"
    assert dates[skipped["id"]] == "2026-11-06"
    assert (
        monday["items"]
        == (
            await client.get("/api/plan", params={"start": "2026-11-03", "end": "2026-11-03"})
        ).json()[0]["items"]
    )


async def test_conflict_is_not_applied_until_a_resolution_is_chosen(client: AsyncClient) -> None:
    await _register(client, "user@example.com")
    monday = await _add(client, "2026-11-02", name="Жим")
    tuesday = await _add(client, "2026-11-03", name="Тяга")
    assert (
        await client.patch(f"/api/plan/{tuesday['id']}", json={"status": "done"})
    ).status_code == 200

    body = {"operation": "shift_only", "entry_id": monday["id"], "days": 1}
    preview = await client.post("/api/plan/shift/preview", json=body)
    assert preview.status_code == 200, preview.text
    assert preview.json()["conflicts"][0]["reason"] == "occupied"
    assert preview.json()["resolutions"] == ["cascade", "stack", "cancel"]
    assert preview.json()["changes"][0]["date_before"] == "2026-11-02"
    assert preview.json()["changes"][0]["date_after"] == "2026-11-03"

    refused = await client.post("/api/plan/shift/apply", json=body)
    assert refused.status_code == 409
    assert (await _dates(client))[monday["id"]] == "2026-11-02"

    cancelled = await client.post("/api/plan/shift/apply", json={**body, "resolution": "cancel"})
    assert cancelled.status_code == 200
    assert cancelled.json()["applied"] is False
    assert (await client.get("/api/plan/shift/history")).json() == []

    stacked = await client.post("/api/plan/shift/apply", json={**body, "resolution": "stack"})
    assert stacked.status_code == 200, stacked.text
    listed = (
        await client.get("/api/plan", params={"start": "2026-11-03", "end": "2026-11-03"})
    ).json()
    assert {entry["name"] for entry in listed} == {"Жим", "Тяга"}


async def test_rest_conflict_cannot_be_stacked(client: AsyncClient) -> None:
    await _register(client, "user@example.com")
    monday = await _add(client, "2026-11-02", name="Жим")
    rest = await _add(client, "2026-11-03", kind="rest")
    assert (
        await client.patch(f"/api/plan/{rest['id']}", json={"is_fixed": True})
    ).status_code == 200

    body = {"operation": "shift_only", "entry_id": monday["id"], "days": 1}
    preview = await client.post("/api/plan/shift/preview", json=body)
    assert preview.json()["conflicts"][0]["reason"] == "blocked"
    assert preview.json()["resolutions"] == ["cascade", "cancel"]

    stacked = await client.post("/api/plan/shift/apply", json={**body, "resolution": "stack"})
    assert stacked.status_code == 409
    cascaded = await client.post("/api/plan/shift/apply", json={**body, "resolution": "cascade"})
    assert cascaded.status_code == 200, cascaded.text
    assert (await _dates(client))[monday["id"]] == "2026-11-04"


async def _dates_entries(client: AsyncClient) -> dict[str, list[dict]]:
    response = await client.get("/api/plan", params={"start": "2026-11-01", "end": "2026-11-30"})
    assert response.status_code == 200, response.text
    return _by_date(response.json())


async def test_shift_only_skip_swap_and_undo(client: AsyncClient) -> None:
    await _register(client, "user@example.com")
    monday = await _add(client, "2026-11-02", name="Понедельник")
    wednesday = await _add(client, "2026-11-04", name="Среда")

    only = await client.post(
        "/api/plan/shift/apply",
        json={"operation": "shift_only", "entry_id": monday["id"], "days": 1},
    )
    assert only.status_code == 200, only.text
    dates = await _dates(client)
    assert dates[monday["id"]] == "2026-11-03"
    assert dates[wednesday["id"]] == "2026-11-04"

    undo = await client.post("/api/plan/shift/undo")
    assert undo.status_code == 200, undo.text
    assert undo.json()["changes"][0]["date_after"] == "2026-11-02"
    assert (await _dates(client))[monday["id"]] == "2026-11-02"
    assert (await client.post("/api/plan/shift/undo")).status_code == 404

    skipped = await client.post(
        "/api/plan/shift/apply", json={"operation": "skip", "entry_id": monday["id"]}
    )
    assert skipped.status_code == 200, skipped.text
    assert skipped.json()["changes"][0]["status_after"] == "skipped"
    listed = await _dates_entries(client)
    assert listed["2026-11-02"][0]["status"] == "skipped"
    assert listed["2026-11-04"][0]["date"] == "2026-11-04"

    await client.post("/api/plan/shift/undo")
    assert (await _dates_entries(client))["2026-11-02"][0]["status"] == "planned"

    swapped = await client.post(
        "/api/plan/shift/apply",
        json={"operation": "swap", "entry_id": monday["id"], "other_id": wednesday["id"]},
    )
    assert swapped.status_code == 200, swapped.text
    dates = await _dates(client)
    assert dates[monday["id"]] == "2026-11-04"
    assert dates[wednesday["id"]] == "2026-11-02"

    await client.post("/api/plan/shift/undo")
    dates = await _dates(client)
    assert dates[monday["id"]] == "2026-11-02"
    assert dates[wednesday["id"]] == "2026-11-04"


async def test_done_workout_and_foreign_entry_are_rejected(client: AsyncClient) -> None:
    await _register(client, "user@example.com")
    done = await _add(client, "2026-11-02", name="Сделана")
    assert (
        await client.patch(f"/api/plan/{done['id']}", json={"status": "done"})
    ).status_code == 200
    refused = await client.post(
        "/api/plan/shift/preview",
        json={"operation": "shift_following", "entry_id": done["id"], "days": 1},
    )
    assert refused.status_code == 422

    assert (await client.post("/api/auth/logout")).status_code == 204
    await _register(client, "other@example.com")
    foreign = await client.post(
        "/api/plan/shift/preview",
        json={"operation": "shift_only", "entry_id": done["id"], "days": 1},
    )
    assert foreign.status_code == 404


async def test_history_keeps_the_latest_twenty_operations(client: AsyncClient) -> None:
    await _register(client, "user@example.com")
    entry = await _add(client, "2026-11-02", name="Цикл")
    for _ in range(HISTORY_LIMIT + 1):
        response = await client.post(
            "/api/plan/shift/apply",
            json={"operation": "shift_only", "entry_id": entry["id"], "days": 1},
        )
        assert response.status_code == 200, response.text

    history = (await client.get("/api/plan/shift/history")).json()
    assert len(history) == HISTORY_LIMIT
    assert history[0]["operation"] == "shift_only"
    assert history[0]["change_count"] == 1

    for _ in range(HISTORY_LIMIT):
        assert (await client.post("/api/plan/shift/undo")).status_code == 200

    assert (await client.get("/api/plan/shift/history")).json() == []
    # Самый старый сдвиг вытеснен из журнала и не откатывается.
    assert (await _dates(client))[entry["id"]] == "2026-11-03"
    assert (await client.post("/api/plan/shift/undo")).status_code == 404


async def test_undo_refuses_to_stack_a_workout_on_a_new_rest_day(client: AsyncClient) -> None:
    await _register(client, "user@example.com")
    monday = await _add(client, "2026-11-02", name="Жим")
    moved = await client.post(
        "/api/plan/shift/apply",
        json={"operation": "shift_only", "entry_id": monday["id"], "days": 2},
    )
    assert moved.status_code == 200, moved.text
    rest = await _add(client, "2026-11-02", kind="rest")

    undo = await client.post("/api/plan/shift/undo")
    assert undo.status_code == 409
    dates = await _dates(client)
    assert dates[monday["id"]] == "2026-11-04"
    assert dates[rest["id"]] == "2026-11-02"
    assert (await client.get("/api/plan/shift/history")).json() != []
