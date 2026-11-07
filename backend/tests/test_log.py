import uuid

from httpx import AsyncClient

BENCH = {
    "name": "Жим штанги лёжа",
    "primary_muscle": "chest",
    "secondary_muscles": ["triceps"],
    "equipment": "barbell",
    "weight_type": "standard",
    "weight_unit": "kg",
    "weight_step": 2.5,
    "rep_min": 8,
    "rep_max": 12,
}

DUMBBELL = {
    **BENCH,
    "name": "Жим гантелей",
    "equipment": "dumbbell",
    "weight_type": "per_dumbbell",
    "secondary_muscles": [],
}

ASSISTED = {
    **BENCH,
    "name": "Подтягивания в гравитроне",
    "primary_muscle": "back",
    "secondary_muscles": [],
    "equipment": "machine",
    "weight_type": "bodyweight_assisted",
}


async def _register(client: AsyncClient, email: str = "user@example.com") -> None:
    response = await client.post(
        "/api/auth/register", json={"email": email, "password": "password1"}
    )
    assert response.status_code == 201


async def _exercise(client: AsyncClient, body: dict | None = None) -> str:
    response = await client.post("/api/exercises", json=body or BENCH)
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _set(rep_min: int = 8, rep_max: int = 12) -> dict:
    return {"rep_min": rep_min, "rep_max": rep_max, "target_rir": 2, "rest_seconds": 90}


async def _plan_workout(client: AsyncClient, exercise_id: str, day: str = "2026-11-10") -> dict:
    template = await client.post(
        "/api/workouts",
        json={"name": "День A", "items": [{"exercise_id": exercise_id, "sets": [_set(), _set()]}]},
    )
    assert template.status_code == 201, template.text
    entry = await client.post(
        "/api/plan/entries", json={"date": day, "template_id": template.json()["id"]}
    )
    assert entry.status_code == 201, entry.text
    return entry.json()


async def _start(client: AsyncClient, planned_id: str) -> tuple[int, dict]:
    response = await client.post("/api/performed", json={"planned_id": planned_id})
    assert response.status_code in (200, 201), response.text
    return response.status_code, response.json()


def _values(**extra: object) -> dict:
    body = {
        "weight": None,
        "extra_weight": None,
        "reps": None,
        "rir": None,
        "is_warmup": False,
        "is_assisted": False,
        "is_negative": False,
        "note": None,
    }
    body.update(extra)
    return body


async def test_log_requires_login(client: AsyncClient) -> None:
    fake = uuid.uuid4()
    assert (await client.post("/api/performed", json={"planned_id": str(fake)})).status_code == 401
    previous = await client.get("/api/performed/previous", params={"exercise_id": str(fake)})
    assert previous.status_code == 401
    saved = await client.put(f"/api/performed/{fake}/sets/{fake}", json=_values())
    assert saved.status_code == 401
    assert (await client.delete(f"/api/performed/{fake}/sets/{fake}")).status_code == 401


async def test_start_copies_plan_and_resumes_same_log(client: AsyncClient) -> None:
    await _register(client)
    exercise_id = await _exercise(client)
    planned = await _plan_workout(client, exercise_id)

    status, workout = await _start(client, planned["id"])

    assert status == 201
    assert workout["planned_id"] == planned["id"]
    assert workout["date"] == "2026-11-10"
    assert workout["name"] == "День A"
    assert workout["finished_at"] is None
    [item] = workout["items"]
    assert item["name"] == "Жим штанги лёжа"
    assert item["weight_step"] == 2.5
    assert item["targets"] == [_set(), _set()]
    assert [logged["position"] for logged in item["sets"]] == [0, 1]
    assert item["sets"][0]["reps"] is None

    again_status, again = await _start(client, planned["id"])
    assert again_status == 200
    assert again["id"] == workout["id"]
    assert len(again["items"][0]["sets"]) == 2


async def test_other_user_and_rest_day_cannot_start(client: AsyncClient) -> None:
    await _register(client)
    exercise_id = await _exercise(client)
    planned = await _plan_workout(client, exercise_id)
    rest = await client.post("/api/plan/entries", json={"date": "2026-11-11", "kind": "rest"})
    assert rest.status_code == 201

    missing = await client.post("/api/performed", json={"planned_id": str(uuid.uuid4())})
    assert missing.status_code == 404
    rest_log = await client.post("/api/performed", json={"planned_id": rest.json()["id"]})
    assert rest_log.status_code == 422

    await client.post("/api/auth/logout")
    await _register(client, "other@example.com")
    hidden = await client.post("/api/performed", json={"planned_id": planned["id"]})
    assert hidden.status_code == 404


async def test_upsert_add_and_delete_sets(client: AsyncClient) -> None:
    await _register(client)
    exercise_id = await _exercise(client)
    planned = await _plan_workout(client, exercise_id)
    _, workout = await _start(client, planned["id"])
    item = workout["items"][0]
    first, second = item["sets"]

    saved = await client.put(
        f"/api/performed/{workout['id']}/sets/{first['id']}",
        json=_values(weight=80, reps=10, rir=5, note="  узкий хват  "),
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["weight"] == 80
    assert saved.json()["reps"] == 10
    assert saved.json()["rir"] == 5
    assert saved.json()["note"] == "узкий хват"

    created = await client.post(
        f"/api/performed/{workout['id']}/items/{item['id']}/sets",
        json={"id": str(uuid.uuid4()), "position": 1, "weight": 70, "reps": 12},
    )
    assert created.status_code == 201, created.text
    replay = await client.post(
        f"/api/performed/{workout['id']}/items/{item['id']}/sets",
        json={"id": created.json()["id"], "reps": 1},
    )
    assert replay.status_code == 200
    assert replay.json()["reps"] == 12
    assert replay.json()["id"] == created.json()["id"]

    removed = await client.delete(f"/api/performed/{workout['id']}/sets/{second['id']}")
    assert removed.status_code == 204

    _, after = await _start(client, planned["id"])
    positions = [logged["position"] for logged in after["items"][0]["sets"]]
    assert positions == [0, 1]
    assert created.json()["id"] in {logged["id"] for logged in after["items"][0]["sets"]}
    assert second["id"] not in {logged["id"] for logged in after["items"][0]["sets"]}


async def test_replace_exercise_and_previous_values(client: AsyncClient) -> None:
    await _register(client)
    bench = await _exercise(client)
    dumbbell = await _exercise(client, DUMBBELL)
    first_day = await _plan_workout(client, bench, "2026-11-01")
    _, earlier = await _start(client, first_day["id"])
    earlier_set = earlier["items"][0]["sets"][0]
    await client.put(
        f"/api/performed/{earlier['id']}/sets/{earlier_set['id']}",
        json=_values(weight=60, reps=8, rir=2),
    )
    await client.post(f"/api/performed/{earlier['id']}/finish")

    second_day = await _plan_workout(client, bench, "2026-11-08")
    _, current = await _start(client, second_day["id"])
    item = current["items"][0]

    previous = await client.get(
        "/api/performed/previous",
        params={"exercise_id": bench, "exclude_id": current["id"]},
    )
    assert previous.status_code == 200, previous.text
    assert previous.json()["date"] == "2026-11-01"
    assert previous.json()["sets"][0]["weight"] == 60
    assert previous.json()["sets"][0]["reps"] == 8

    # Текущая тренировка в «прошлый раз» не попадает, даже если в ней уже есть цифры.
    await client.put(
        f"/api/performed/{current['id']}/sets/{item['sets'][0]['id']}",
        json=_values(weight=100, reps=3),
    )
    excluded = await client.get(
        "/api/performed/previous",
        params={"exercise_id": bench, "exclude_id": current["id"]},
    )
    assert excluded.json()["performed_id"] == earlier["id"]

    replaced = await client.put(
        f"/api/performed/{current['id']}/items/{item['id']}/exercise",
        json={"exercise_id": dumbbell},
    )
    assert replaced.status_code == 200, replaced.text
    assert replaced.json()["items"][0]["name"] == "Жим гантелей"
    assert replaced.json()["items"][0]["weight_type"] == "per_dumbbell"
    assert replaced.json()["items"][0]["targets"] == []
    assert replaced.json()["items"][0]["sets"][0]["exercise_id"] == dumbbell

    missing = await client.put(
        f"/api/performed/{current['id']}/items/{item['id']}/exercise",
        json={"exercise_id": str(uuid.uuid4())},
    )
    assert missing.status_code == 404


async def test_finish_counts_working_sets_and_marks_plan_done(client: AsyncClient) -> None:
    await _register(client)
    exercise_id = await _exercise(client, DUMBBELL)
    assisted = await _exercise(client, ASSISTED)
    planned = await _plan_workout(client, exercise_id)
    _, workout = await _start(client, planned["id"])
    item = workout["items"][0]
    warmup, working = item["sets"]
    await client.put(
        f"/api/performed/{workout['id']}/sets/{warmup['id']}",
        json=_values(weight=10, reps=15, is_warmup=True),
    )
    await client.put(
        f"/api/performed/{workout['id']}/sets/{working['id']}",
        json=_values(weight=24, reps=10),
    )
    added = await client.post(
        f"/api/performed/{workout['id']}/items",
        json={"exercise_id": assisted},
    )
    assert added.status_code == 201, added.text
    assisted_set = added.json()["items"][1]["sets"][0]
    await client.put(
        f"/api/performed/{workout['id']}/sets/{assisted_set['id']}",
        json=_values(weight=40, reps=6),
    )

    finished = await client.post(f"/api/performed/{workout['id']}/finish")
    assert finished.status_code == 200, finished.text
    body = finished.json()
    assert body["finished_at"] is not None
    # Гантель 24 × 2 × 10. Помощь гравитрона в объём не входит и единицу не подменяет.
    assert body["summary"]["working_sets"] == 2
    assert body["summary"]["volume"] == 480
    assert body["summary"]["unit"] == "kg"

    plan = await client.get("/api/plan", params={"start": "2026-11-10", "end": "2026-11-10"})
    assert plan.json()[0]["status"] == "done"


async def test_notes_and_skipped_plan_stay_put(client: AsyncClient) -> None:
    await _register(client)
    exercise_id = await _exercise(client)
    planned = await _plan_workout(client, exercise_id)
    await client.patch(f"/api/plan/{planned['id']}", json={"status": "skipped"})
    _, workout = await _start(client, planned["id"])
    item = workout["items"][0]

    note = await client.patch(f"/api/performed/{workout['id']}", json={"note": "  спал мало  "})
    assert note.json()["note"] == "спал мало"
    item_note = await client.patch(
        f"/api/performed/{workout['id']}/items/{item['id']}",
        json={"note": "скамья на 2"},
    )
    assert item_note.json()["items"][0]["note"] == "скамья на 2"

    await client.post(f"/api/performed/{workout['id']}/finish")
    plan = await client.get("/api/plan", params={"start": "2026-11-10", "end": "2026-11-10"})
    assert plan.json()[0]["status"] == "skipped"


async def test_deleting_plan_entry_keeps_the_log(client: AsyncClient) -> None:
    await _register(client)
    exercise_id = await _exercise(client)
    planned = await _plan_workout(client, exercise_id)
    _, workout = await _start(client, planned["id"])
    await client.put(
        f"/api/performed/{workout['id']}/sets/{workout['items'][0]['sets'][0]['id']}",
        json=_values(weight=50, reps=5),
    )

    assert (await client.delete(f"/api/plan/{planned['id']}")).status_code == 204

    # Старт по удалённому плану больше не находится, а сам факт остаётся доступен через подход.
    missing = await client.post("/api/performed", json={"planned_id": planned["id"]})
    assert missing.status_code == 404
    saved = await client.put(
        f"/api/performed/{workout['id']}/sets/{workout['items'][0]['sets'][0]['id']}",
        json=_values(weight=55, reps=5),
    )
    assert saved.status_code == 200
    assert saved.json()["weight"] == 55
