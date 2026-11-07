import uuid

from httpx import AsyncClient

BENCH_BODY = {
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


async def _register(client: AsyncClient, email: str) -> None:
    response = await client.post(
        "/api/auth/register",
        json={"email": email, "password": "password1"},
    )
    assert response.status_code == 201


async def _exercise(client: AsyncClient) -> str:
    response = await client.post("/api/exercises", json=BENCH_BODY)
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _set(rep_min: int = 8, rep_max: int = 12) -> dict:
    return {"rep_min": rep_min, "rep_max": rep_max, "target_rir": 2, "rest_seconds": 120}


async def _template(client: AsyncClient, name: str = "День A") -> dict:
    bench = await _exercise(client)
    response = await client.post(
        "/api/workouts",
        json={"name": name, "items": [{"exercise_id": bench, "sets": [_set(3, 5), _set()]}]},
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _add_from_template(client: AsyncClient, template_id: str, day: str) -> dict:
    response = await client.post(
        "/api/plan/entries", json={"date": day, "template_id": template_id}
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _range(client: AsyncClient, start: str, end: str) -> list[dict]:
    response = await client.get("/api/plan", params={"start": start, "end": end})
    assert response.status_code == 200, response.text
    return response.json()


async def test_plan_requires_login(client: AsyncClient) -> None:
    fake_id = uuid.uuid4()
    assert (
        await client.get("/api/plan", params={"start": "2026-11-01", "end": "2026-11-30"})
    ).status_code == 401
    assert (
        await client.post("/api/plan/entries", json={"date": "2026-11-01", "name": "День"})
    ).status_code == 401
    assert (await client.patch(f"/api/plan/{fake_id}", json={"status": "done"})).status_code == 401
    assert (await client.delete(f"/api/plan/{fake_id}")).status_code == 401


async def test_add_from_library_copies_snapshot(client: AsyncClient) -> None:
    await _register(client, "user@example.com")
    template = await _template(client)

    entry = await _add_from_template(client, template["id"], "2026-11-10")

    assert entry["kind"] == "workout"
    assert entry["status"] == "planned"
    assert entry["is_fixed"] is False
    assert entry["name"] == "День A"
    assert entry["template_id"] == template["id"]
    assert entry["date"] == "2026-11-10"
    [item] = entry["items"]
    assert item["exercise"]["name"] == "Жим штанги лёжа"
    assert item["exercise"]["weight_step"] == 2.5
    assert [(s["rep_min"], s["rep_max"]) for s in item["sets"]] == [(3, 5), (8, 12)]


async def test_template_edits_do_not_change_plan(client: AsyncClient) -> None:
    await _register(client, "user@example.com")
    template = await _template(client)
    entry = await _add_from_template(client, template["id"], "2026-11-10")
    bench = entry["items"][0]["exercise"]["exercise_id"]

    await client.put(
        f"/api/workouts/{template['id']}",
        json={"name": "Другая", "items": [{"exercise_id": bench, "sets": [_set(1, 1)]}]},
    )
    await client.patch(
        f"/api/workouts/{template['id']}",
        json={"name": "Переименована"},
    )

    [planned] = await _range(client, "2026-11-10", "2026-11-10")
    assert planned["name"] == "День A"
    assert planned["items"] == entry["items"]


async def test_deleting_template_keeps_planned_workout(client: AsyncClient) -> None:
    await _register(client, "user@example.com")
    template = await _template(client)
    entry = await _add_from_template(client, template["id"], "2026-11-10")

    assert (await client.delete(f"/api/workouts/{template['id']}")).status_code == 204

    [planned] = await _range(client, "2026-11-10", "2026-11-10")
    assert planned["id"] == entry["id"]
    assert planned["template_id"] is None
    assert planned["items"] == entry["items"]


async def test_add_from_scratch_by_name(client: AsyncClient) -> None:
    await _register(client, "user@example.com")

    response = await client.post(
        "/api/plan/entries", json={"date": "2026-11-11", "name": "  Свободная  "}
    )
    assert response.status_code == 201
    entry = response.json()
    assert entry["name"] == "Свободная"
    assert entry["template_id"] is None
    assert entry["items"] == []


async def test_rest_day_and_workout_cannot_share_a_day(client: AsyncClient) -> None:
    await _register(client, "user@example.com")
    template = await _template(client)

    rest = await client.post("/api/plan/entries", json={"date": "2026-11-12", "kind": "rest"})
    assert rest.status_code == 201
    assert rest.json()["kind"] == "rest"
    assert rest.json()["items"] == []

    workout = await client.post(
        "/api/plan/entries", json={"date": "2026-11-12", "template_id": template["id"]}
    )
    assert workout.status_code == 409

    second_rest = await client.post(
        "/api/plan/entries", json={"date": "2026-11-12", "kind": "rest"}
    )
    assert second_rest.status_code == 409


async def test_two_workouts_can_share_a_day(client: AsyncClient) -> None:
    await _register(client, "user@example.com")
    template = await _template(client)

    await _add_from_template(client, template["id"], "2026-11-13")
    await client.post("/api/plan/entries", json={"date": "2026-11-13", "name": "Растяжка"})

    entries = await _range(client, "2026-11-13", "2026-11-13")
    assert [e["position"] for e in entries] == [0, 1]
    assert [e["name"] for e in entries] == ["День A", "Растяжка"]


async def test_entry_body_validation(client: AsyncClient) -> None:
    await _register(client, "user@example.com")
    template = await _template(client)

    invalid_bodies = [
        {"date": "2026-11-01"},
        {"date": "2026-11-01", "name": "День", "template_id": template["id"]},
        {"date": "2026-11-01", "kind": "rest", "name": "День"},
        {"date": "2026-11-01", "kind": "unknown", "name": "День"},
        {"date": "not-a-date", "name": "День"},
    ]
    for body in invalid_bodies:
        response = await client.post("/api/plan/entries", json=body)
        assert response.status_code == 422, body
    assert await _range(client, "2026-11-01", "2026-11-30") == []


async def test_foreign_template_is_rejected(client: AsyncClient) -> None:
    await _register(client, "first@example.com")
    template = await _template(client)
    await client.post("/api/auth/logout")

    await _register(client, "second@example.com")
    response = await client.post(
        "/api/plan/entries", json={"date": "2026-11-10", "template_id": template["id"]}
    )
    assert response.status_code == 422


async def test_range_returns_own_entries_sorted_by_date(client: AsyncClient) -> None:
    await _register(client, "user@example.com")
    await client.post("/api/plan/entries", json={"date": "2026-11-20", "name": "Поздняя"})
    await client.post("/api/plan/entries", json={"date": "2026-11-05", "name": "Ранняя"})
    await client.post("/api/plan/entries", json={"date": "2026-12-01", "name": "Вне диапазона"})

    entries = await _range(client, "2026-11-01", "2026-11-30")
    assert [e["name"] for e in entries] == ["Ранняя", "Поздняя"]


async def test_range_boundaries_are_inclusive_and_validated(client: AsyncClient) -> None:
    await _register(client, "user@example.com")
    await client.post("/api/plan/entries", json={"date": "2026-11-01", "name": "Первый"})
    await client.post("/api/plan/entries", json={"date": "2026-11-30", "name": "Последний"})

    assert len(await _range(client, "2026-11-01", "2026-11-30")) == 2
    assert (
        await client.get("/api/plan", params={"start": "2026-11-30", "end": "2026-11-01"})
    ).status_code == 422
    assert (
        await client.get("/api/plan", params={"start": "2026-01-01", "end": "2027-12-31"})
    ).status_code == 422


async def test_move_changes_date_and_appends_to_target_day(client: AsyncClient) -> None:
    await _register(client, "user@example.com")
    await client.post("/api/plan/entries", json={"date": "2026-11-15", "name": "Уже тут"})
    entry = (
        await client.post("/api/plan/entries", json={"date": "2026-11-10", "name": "Переезд"})
    ).json()

    response = await client.patch(f"/api/plan/{entry['id']}", json={"date": "2026-11-15"})
    assert response.status_code == 200, response.text
    assert response.json()["date"] == "2026-11-15"
    assert response.json()["position"] == 1
    assert await _range(client, "2026-11-10", "2026-11-10") == []
    assert [e["name"] for e in await _range(client, "2026-11-15", "2026-11-15")] == [
        "Уже тут",
        "Переезд",
    ]


async def test_done_and_skipped_workouts_cannot_be_moved(client: AsyncClient) -> None:
    await _register(client, "user@example.com")
    entry = (
        await client.post("/api/plan/entries", json={"date": "2026-11-10", "name": "День"})
    ).json()

    assert (
        await client.patch(f"/api/plan/{entry['id']}", json={"status": "done"})
    ).status_code == 200
    response = await client.patch(f"/api/plan/{entry['id']}", json={"date": "2026-11-11"})
    assert response.status_code == 409
    assert (await _range(client, "2026-11-10", "2026-11-10"))[0]["status"] == "done"


async def test_workout_cannot_be_moved_onto_rest_day_and_back(client: AsyncClient) -> None:
    await _register(client, "user@example.com")
    workout = (
        await client.post("/api/plan/entries", json={"date": "2026-11-10", "name": "День"})
    ).json()
    rest = (
        await client.post("/api/plan/entries", json={"date": "2026-11-12", "kind": "rest"})
    ).json()

    assert (
        await client.patch(f"/api/plan/{workout['id']}", json={"date": "2026-11-12"})
    ).status_code == 409
    assert (
        await client.patch(f"/api/plan/{rest['id']}", json={"date": "2026-11-10"})
    ).status_code == 409

    # Отдых можно перенести на пустой день.
    moved = await client.patch(f"/api/plan/{rest['id']}", json={"date": "2026-11-14"})
    assert moved.status_code == 200
    assert moved.json()["date"] == "2026-11-14"


async def test_rest_day_has_no_status(client: AsyncClient) -> None:
    await _register(client, "user@example.com")
    rest = (
        await client.post("/api/plan/entries", json={"date": "2026-11-12", "kind": "rest"})
    ).json()
    assert rest["status"] is None

    response = await client.patch(f"/api/plan/{rest['id']}", json={"status": "done"})
    assert response.status_code == 409
    assert (await _range(client, "2026-11-12", "2026-11-12"))[0]["status"] is None


async def test_status_and_fixed_flag_update(client: AsyncClient) -> None:
    await _register(client, "user@example.com")
    entry = (
        await client.post("/api/plan/entries", json={"date": "2026-11-10", "name": "День"})
    ).json()

    for status in ["done", "planned", "skipped", "planned", "moved", "planned"]:
        response = await client.patch(f"/api/plan/{entry['id']}", json={"status": status})
        assert response.status_code == 200
        assert response.json()["status"] == status

    response = await client.patch(f"/api/plan/{entry['id']}", json={"is_fixed": True})
    assert response.json()["is_fixed"] is True
    response = await client.patch(f"/api/plan/{entry['id']}", json={"status": "unknown"})
    assert response.status_code == 422


async def test_final_status_cannot_jump_to_another_final_status(client: AsyncClient) -> None:
    await _register(client, "user@example.com")
    entry = (
        await client.post("/api/plan/entries", json={"date": "2026-11-10", "name": "День"})
    ).json()
    await client.patch(f"/api/plan/{entry['id']}", json={"status": "done"})

    response = await client.patch(f"/api/plan/{entry['id']}", json={"status": "skipped"})
    assert response.status_code == 409
    # Повтор того же статуса — не ошибка.
    response = await client.patch(f"/api/plan/{entry['id']}", json={"status": "done"})
    assert response.status_code == 200
    assert (await _range(client, "2026-11-10", "2026-11-10"))[0]["status"] == "done"


async def test_moved_status_entry_cannot_be_moved_until_planned_again(
    client: AsyncClient,
) -> None:
    await _register(client, "user@example.com")
    entry = (
        await client.post("/api/plan/entries", json={"date": "2026-11-10", "name": "День"})
    ).json()
    await client.patch(f"/api/plan/{entry['id']}", json={"status": "moved"})

    response = await client.patch(f"/api/plan/{entry['id']}", json={"date": "2026-11-11"})
    assert response.status_code == 409
    await client.patch(f"/api/plan/{entry['id']}", json={"status": "planned"})
    response = await client.patch(f"/api/plan/{entry['id']}", json={"date": "2026-11-11"})
    assert response.status_code == 200


async def test_cycle_creates_entries_on_selected_weekdays(client: AsyncClient) -> None:
    await _register(client, "user@example.com")
    template = await _template(client)

    # 2026-11-02 — понедельник. Пн, ср, пт на 2 недели: 6 записей.
    response = await client.post(
        "/api/plan/cycles",
        json={
            "template_id": template["id"],
            "start_date": "2026-11-02",
            "weekdays": [0, 2, 4],
            "weeks": 2,
        },
    )
    assert response.status_code == 201, response.text
    dates = [entry["date"] for entry in response.json()]
    assert dates == [
        "2026-11-02",
        "2026-11-04",
        "2026-11-06",
        "2026-11-09",
        "2026-11-11",
        "2026-11-13",
    ]
    assert all(entry["name"] == "День A" for entry in response.json())
    assert all(len(entry["items"]) == 1 for entry in response.json())


async def test_cycle_is_refused_if_any_day_is_rest(client: AsyncClient) -> None:
    await _register(client, "user@example.com")
    template = await _template(client)
    await client.post("/api/plan/entries", json={"date": "2026-11-09", "kind": "rest"})

    response = await client.post(
        "/api/plan/cycles",
        json={
            "template_id": template["id"],
            "start_date": "2026-11-02",
            "weekdays": [0, 2, 4],
            "weeks": 2,
        },
    )
    assert response.status_code == 409
    # Ни одна тренировка цикла не создана: в месяце осталась только запись об отдыхе.
    entries = await _range(client, "2026-11-01", "2026-11-30")
    assert [(e["date"], e["kind"]) for e in entries] == [("2026-11-09", "rest")]


async def test_cycle_validation(client: AsyncClient) -> None:
    await _register(client, "user@example.com")
    template = await _template(client)
    base = {"template_id": template["id"], "start_date": "2026-11-02", "weekdays": [0], "weeks": 1}

    invalid = [
        {**base, "weekdays": []},
        {**base, "weekdays": [7]},
        {**base, "weekdays": [0, 0]},
        {**base, "weeks": 0},
        {**base, "weeks": 53},
        {**base, "template_id": str(uuid.uuid4())},
    ]
    for body in invalid:
        response = await client.post("/api/plan/cycles", json=body)
        assert response.status_code == 422, body


async def test_delete_removes_entry(client: AsyncClient) -> None:
    await _register(client, "user@example.com")
    entry = (
        await client.post("/api/plan/entries", json={"date": "2026-11-10", "name": "День"})
    ).json()

    assert (await client.delete(f"/api/plan/{entry['id']}")).status_code == 204
    assert await _range(client, "2026-11-10", "2026-11-10") == []
    assert (await client.delete(f"/api/plan/{entry['id']}")).status_code == 404


async def test_plan_is_isolated_between_users(client: AsyncClient) -> None:
    await _register(client, "first@example.com")
    entry = (
        await client.post("/api/plan/entries", json={"date": "2026-11-10", "name": "Мой"})
    ).json()
    await client.post("/api/auth/logout")

    await _register(client, "second@example.com")
    assert await _range(client, "2026-11-01", "2026-11-30") == []
    assert (
        await client.patch(f"/api/plan/{entry['id']}", json={"status": "done"})
    ).status_code == 404
    assert (await client.delete(f"/api/plan/{entry['id']}")).status_code == 404

    # Чужая запись не меняется: у владельца статус прежний.
    await client.post("/api/auth/logout")
    await client.post(
        "/api/auth/login", json={"email": "first@example.com", "password": "password1"}
    )
    assert (await _range(client, "2026-11-10", "2026-11-10"))[0]["status"] == "planned"


async def test_unknown_entry_returns_404(client: AsyncClient) -> None:
    await _register(client, "user@example.com")
    missing = uuid.uuid4()

    assert (await client.patch(f"/api/plan/{missing}", json={"status": "done"})).status_code == 404
    assert (await client.delete(f"/api/plan/{missing}")).status_code == 404


async def test_moved_entry_leaves_old_range_and_appears_in_new_one(client: AsyncClient) -> None:
    await _register(client, "user@example.com")
    template = await _template(client)
    entry = await _add_from_template(client, template["id"], "2026-11-10")

    response = await client.patch(f"/api/plan/{entry['id']}", json={"date": "2026-12-03"})
    assert response.status_code == 200, response.text

    assert await _range(client, "2026-11-01", "2026-11-30") == []
    [moved] = await _range(client, "2026-12-01", "2026-12-31")
    assert moved["id"] == entry["id"]
    assert moved["date"] == "2026-12-03"


async def test_deleting_exercise_keeps_planned_snapshot(client: AsyncClient) -> None:
    await _register(client, "user@example.com")
    template = await _template(client)
    entry = await _add_from_template(client, template["id"], "2026-11-10")
    exercise_id = entry["items"][0]["exercise"]["exercise_id"]

    # Упражнение нельзя удалить, пока оно в шаблоне; после удаления шаблона — можно.
    assert (await client.delete(f"/api/exercises/{exercise_id}")).status_code == 409
    assert (await client.delete(f"/api/workouts/{template['id']}")).status_code == 204
    assert (await client.delete(f"/api/exercises/{exercise_id}")).status_code == 204

    [planned] = await _range(client, "2026-11-10", "2026-11-10")
    assert planned["items"] == entry["items"]
    assert planned["items"][0]["exercise"]["name"] == "Жим штанги лёжа"
