import uuid

from httpx import AsyncClient

BENCH = {
    "name": "  Жим штанги лёжа  ",
    "primary_muscle": "chest",
    "secondary_muscles": ["triceps", "shoulders"],
    "equipment": "barbell",
    "weight_type": "standard",
    "weight_unit": "kg",
    "weight_step": 2.5,
    "rep_min": 8,
    "rep_max": 12,
}

ROW = {
    "name": "Тяга верхнего блока",
    "primary_muscle": "back",
    "secondary_muscles": [],
    "equipment": "cable",
    "weight_type": "stack",
    "weight_unit": "kg",
    "weight_step": 5,
    "rep_min": 10,
    "rep_max": 15,
}


async def _register(client: AsyncClient, email: str) -> None:
    response = await client.post(
        "/api/auth/register",
        json={"email": email, "password": "password1"},
    )
    assert response.status_code == 201


async def _create(client: AsyncClient, body: dict) -> dict:
    response = await client.post("/api/exercises", json=body)
    assert response.status_code == 201, response.text
    return response.json()


async def test_exercises_require_login(client: AsyncClient) -> None:
    fake_id = uuid.uuid4()
    assert (await client.get("/api/exercises")).status_code == 401
    assert (await client.post("/api/exercises", json=BENCH)).status_code == 401
    assert (await client.get(f"/api/exercises/{fake_id}")).status_code == 401
    assert (await client.put(f"/api/exercises/{fake_id}", json=BENCH)).status_code == 401
    assert (await client.delete(f"/api/exercises/{fake_id}")).status_code == 401


async def test_create_and_read_exercise(client: AsyncClient) -> None:
    await _register(client, "user@example.com")

    created = await _create(client, BENCH)
    assert created["name"] == "Жим штанги лёжа"
    assert created["weight_step"] == 2.5
    assert created["secondary_muscles"] == ["triceps", "shoulders"]

    response = await client.get(f"/api/exercises/{created['id']}")
    assert response.status_code == 200
    assert response.json() == created

    response = await client.get("/api/exercises")
    assert response.json() == [created]


async def test_update_replaces_exercise(client: AsyncClient) -> None:
    await _register(client, "user@example.com")
    created = await _create(client, BENCH)

    body = {**ROW, "weight_unit": "lb", "weight_step": 5}
    response = await client.put(f"/api/exercises/{created['id']}", json=body)
    assert response.status_code == 200
    assert response.json() == {**body, "id": created["id"]}

    response = await client.get(f"/api/exercises/{created['id']}")
    assert response.json()["primary_muscle"] == "back"


async def test_update_rejects_partial_body(client: AsyncClient) -> None:
    await _register(client, "user@example.com")
    created = await _create(client, BENCH)

    response = await client.put(f"/api/exercises/{created['id']}", json={"name": "Другое"})
    assert response.status_code == 422

    response = await client.get(f"/api/exercises/{created['id']}")
    assert response.json()["name"] == "Жим штанги лёжа"


async def test_delete_exercise(client: AsyncClient) -> None:
    await _register(client, "user@example.com")
    created = await _create(client, BENCH)

    response = await client.delete(f"/api/exercises/{created['id']}")
    assert response.status_code == 204

    response = await client.get(f"/api/exercises/{created['id']}")
    assert response.status_code == 404


async def test_search_matches_name_case_insensitively(client: AsyncClient) -> None:
    await _register(client, "user@example.com")
    await _create(client, BENCH)
    await _create(client, ROW)

    response = await client.get("/api/exercises", params={"q": "жим"})
    assert [item["name"] for item in response.json()] == ["Жим штанги лёжа"]

    response = await client.get("/api/exercises", params={"q": "БЛОК"})
    assert [item["name"] for item in response.json()] == ["Тяга верхнего блока"]


async def test_search_treats_wildcards_literally(client: AsyncClient) -> None:
    await _register(client, "user@example.com")
    await _create(client, BENCH)

    response = await client.get("/api/exercises", params={"q": "%"})
    assert response.json() == []

    response = await client.get("/api/exercises", params={"q": "_"})
    assert response.json() == []


async def test_validation_rejects_invalid_values(client: AsyncClient) -> None:
    await _register(client, "user@example.com")

    invalid_bodies = [
        {**BENCH, "name": "   "},
        {**BENCH, "name": "x" * 121},
        {**BENCH, "primary_muscle": "arms"},
        {**BENCH, "equipment": "kettlebell"},
        {**BENCH, "weight_type": "bodyweight_bonus"},
        {**BENCH, "weight_type": "bodyweight_plus"},
        {**BENCH, "equipment": "cable", "weight_type": "standard"},
        {**BENCH, "equipment": "bodyweight", "weight_type": "standard"},
        {**BENCH, "weight_unit": "stone"},
        {**BENCH, "weight_step": 0},
        {**BENCH, "weight_step": -2.5},
        {**BENCH, "weight_step": 101},
        {**BENCH, "rep_min": 0},
        {**BENCH, "rep_min": 13, "rep_max": 12},
        {**BENCH, "secondary_muscles": ["triceps", "triceps"]},
        {**BENCH, "secondary_muscles": ["chest"]},
        {
            **BENCH,
            "secondary_muscles": ["triceps", "shoulders", "biceps", "forearms", "core", "calves"],
        },
    ]
    for body in invalid_bodies:
        response = await client.post("/api/exercises", json=body)
        assert response.status_code == 422, body


async def test_secondary_muscles_default_to_empty(client: AsyncClient) -> None:
    await _register(client, "user@example.com")
    body = {key: value for key, value in BENCH.items() if key != "secondary_muscles"}

    created = await _create(client, body)
    assert created["secondary_muscles"] == []


async def test_exercises_are_isolated_between_users(client: AsyncClient) -> None:
    await _register(client, "first@example.com")
    mine = await _create(client, BENCH)
    await client.post("/api/auth/logout")

    await _register(client, "second@example.com")
    assert (await client.get("/api/exercises")).json() == []

    exercise_id = mine["id"]
    assert (await client.get(f"/api/exercises/{exercise_id}")).status_code == 404
    assert (await client.put(f"/api/exercises/{exercise_id}", json=ROW)).status_code == 404
    assert (await client.delete(f"/api/exercises/{exercise_id}")).status_code == 404

    # Чужое упражнение осталось нетронутым.
    await client.post("/api/auth/logout")
    await client.post(
        "/api/auth/login", json={"email": "first@example.com", "password": "password1"}
    )
    response = await client.get(f"/api/exercises/{exercise_id}")
    assert response.json()["name"] == "Жим штанги лёжа"


async def test_unknown_exercise_returns_404(client: AsyncClient) -> None:
    await _register(client, "user@example.com")
    missing = uuid.uuid4()

    assert (await client.get(f"/api/exercises/{missing}")).status_code == 404
    assert (await client.put(f"/api/exercises/{missing}", json=BENCH)).status_code == 404
    assert (await client.delete(f"/api/exercises/{missing}")).status_code == 404


async def test_malformed_exercise_id_returns_422(client: AsyncClient) -> None:
    await _register(client, "user@example.com")

    response = await client.get("/api/exercises/not-a-uuid")
    assert response.status_code == 422


async def test_weight_type_must_fit_equipment(client: AsyncClient) -> None:
    await _register(client, "user@example.com")
    allowed = {
        "barbell": ["standard"],
        "dumbbell": ["standard", "per_dumbbell"],
        "machine": ["standard", "stack", "stack_plus_extra", "bodyweight_assisted"],
        "cable": ["stack", "stack_plus_extra"],
        "bodyweight": ["bodyweight_plus", "bodyweight_assisted"],
    }
    for equipment, weight_types in allowed.items():
        for weight_type in weight_types:
            body = {**BENCH, "equipment": equipment, "weight_type": weight_type}
            response = await client.post("/api/exercises", json=body)
            assert response.status_code == 201, (equipment, weight_type, response.text)
