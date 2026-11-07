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

ROW_BODY = {
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


async def _exercise(client: AsyncClient, body: dict = BENCH_BODY) -> str:
    response = await client.post("/api/exercises", json=body)
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _set(rep_min: int = 8, rep_max: int = 12, rir: int | None = 2, rest: int | None = 120) -> dict:
    return {"rep_min": rep_min, "rep_max": rep_max, "target_rir": rir, "rest_seconds": rest}


async def _workout(client: AsyncClient, name: str, items: list[dict]) -> dict:
    response = await client.post("/api/workouts", json={"name": name, "items": items})
    assert response.status_code == 201, response.text
    return response.json()


async def test_workouts_require_login(client: AsyncClient) -> None:
    fake_id = uuid.uuid4()
    body = {"name": "День 1", "items": []}
    assert (await client.get("/api/workouts")).status_code == 401
    assert (await client.post("/api/workouts", json=body)).status_code == 401
    assert (await client.get(f"/api/workouts/{fake_id}")).status_code == 401
    assert (await client.put(f"/api/workouts/{fake_id}", json=body)).status_code == 401
    assert (await client.patch(f"/api/workouts/{fake_id}", json={"name": "x"})).status_code == 401
    assert (await client.post(f"/api/workouts/{fake_id}/copy")).status_code == 401
    assert (await client.delete(f"/api/workouts/{fake_id}")).status_code == 401


async def test_create_keeps_exercise_order_and_per_set_targets(client: AsyncClient) -> None:
    await _register(client, "user@example.com")
    bench = await _exercise(client)
    row = await _exercise(client, ROW_BODY)

    created = await _workout(
        client,
        "  День A  ",
        [
            {"exercise_id": row, "sets": [_set(10, 15, None, None)]},
            {
                "exercise_id": bench,
                # Один тяжёлый и три рабочих: подходы различаются.
                "sets": [_set(3, 5, 0, 240), _set(8, 10, 2, 120), _set(8, 10, 2, 120)],
            },
        ],
    )

    assert created["name"] == "День A"
    assert [item["exercise_id"] for item in created["items"]] == [row, bench]
    assert [item["position"] for item in created["items"]] == [0, 1]
    assert created["items"][0]["exercise"]["name"] == "Тяга верхнего блока"

    bench_sets = created["items"][1]["sets"]
    assert [
        (s["rep_min"], s["rep_max"], s["target_rir"], s["rest_seconds"]) for s in bench_sets
    ] == [
        (3, 5, 0, 240),
        (8, 10, 2, 120),
        (8, 10, 2, 120),
    ]
    assert created["items"][0]["sets"][0]["target_rir"] is None

    response = await client.get(f"/api/workouts/{created['id']}")
    assert response.status_code == 200
    assert response.json() == created


async def test_empty_workout_is_allowed(client: AsyncClient) -> None:
    await _register(client, "user@example.com")

    created = await _workout(client, "Пустой", [])
    assert created["items"] == []

    assert (await client.get("/api/workouts")).json() == [created]


async def test_list_returns_only_own_workouts_in_creation_order(client: AsyncClient) -> None:
    await _register(client, "user@example.com")
    first = await _workout(client, "День 1", [])
    second = await _workout(client, "День 2", [])

    response = await client.get("/api/workouts")
    assert [item["id"] for item in response.json()] == [first["id"], second["id"]]


async def test_put_replaces_name_and_items(client: AsyncClient) -> None:
    await _register(client, "user@example.com")
    bench = await _exercise(client)
    row = await _exercise(client, ROW_BODY)
    created = await _workout(client, "День 1", [{"exercise_id": bench, "sets": [_set()]}])

    body = {
        "name": "День 1 — тяга",
        "items": [
            {"exercise_id": row, "sets": [_set(10, 12)]},
            {"exercise_id": bench, "sets": [_set(5, 5)]},
        ],
    }
    response = await client.put(f"/api/workouts/{created['id']}", json=body)
    assert response.status_code == 200, response.text

    updated = response.json()
    assert updated["id"] == created["id"]
    assert updated["name"] == "День 1 — тяга"
    assert [item["exercise_id"] for item in updated["items"]] == [row, bench]
    assert (await client.get(f"/api/workouts/{created['id']}")).json() == updated


async def test_put_reorders_items(client: AsyncClient) -> None:
    await _register(client, "user@example.com")
    bench = await _exercise(client)
    row = await _exercise(client, ROW_BODY)
    created = await _workout(
        client,
        "День 1",
        [{"exercise_id": bench, "sets": [_set()]}, {"exercise_id": row, "sets": [_set()]}],
    )

    reordered = [
        {"exercise_id": row, "sets": [_set()]},
        {"exercise_id": bench, "sets": [_set()]},
    ]
    response = await client.put(
        f"/api/workouts/{created['id']}", json={"name": "День 1", "items": reordered}
    )
    assert [item["exercise_id"] for item in response.json()["items"]] == [row, bench]


async def test_put_with_foreign_exercise_changes_nothing(client: AsyncClient) -> None:
    await _register(client, "first@example.com")
    bench = await _exercise(client)
    created = await _workout(client, "Мой день", [{"exercise_id": bench, "sets": [_set()]}])
    await client.post("/api/auth/logout")

    await _register(client, "second@example.com")
    foreign = await _exercise(client, ROW_BODY)
    await client.post("/api/auth/logout")

    await client.post(
        "/api/auth/login", json={"email": "first@example.com", "password": "password1"}
    )
    body = {
        "name": "Подмена",
        "items": [
            {"exercise_id": bench, "sets": [_set()]},
            {"exercise_id": foreign, "sets": [_set()]},
        ],
    }
    response = await client.put(f"/api/workouts/{created['id']}", json=body)
    assert response.status_code == 422

    current = (await client.get(f"/api/workouts/{created['id']}")).json()
    assert current["name"] == "Мой день"
    assert [item["exercise_id"] for item in current["items"]] == [bench]


async def test_create_with_unknown_exercise_is_rejected(client: AsyncClient) -> None:
    await _register(client, "user@example.com")

    response = await client.post(
        "/api/workouts",
        json={"name": "День", "items": [{"exercise_id": str(uuid.uuid4()), "sets": [_set()]}]},
    )
    assert response.status_code == 422
    assert (await client.get("/api/workouts")).json() == []


async def test_rename_changes_only_the_name(client: AsyncClient) -> None:
    await _register(client, "user@example.com")
    bench = await _exercise(client)
    created = await _workout(client, "День 1", [{"exercise_id": bench, "sets": [_set()]}])

    response = await client.patch(f"/api/workouts/{created['id']}", json={"name": "  Ноги  "})
    assert response.status_code == 200
    assert response.json() == {**created, "name": "Ноги"}


async def test_copy_creates_independent_workout(client: AsyncClient) -> None:
    await _register(client, "user@example.com")
    bench = await _exercise(client)
    row = await _exercise(client, ROW_BODY)
    original = await _workout(
        client,
        "День A",
        [
            {"exercise_id": bench, "sets": [_set(3, 5, 0, 240), _set(8, 10)]},
            {"exercise_id": row, "sets": [_set()]},
        ],
    )

    response = await client.post(f"/api/workouts/{original['id']}/copy")
    assert response.status_code == 201
    copy = response.json()
    assert copy["id"] != original["id"]
    assert copy["name"] == "День A (копия)"
    assert [item["exercise_id"] for item in copy["items"]] == [bench, row]
    assert [len(item["sets"]) for item in copy["items"]] == [2, 1]
    assert copy["items"][0]["sets"][0]["rest_seconds"] == 240
    assert copy["items"][0]["id"] != original["items"][0]["id"]

    # Правка копии не трогает оригинал.
    await client.put(
        f"/api/workouts/{copy['id']}",
        json={"name": "Другой", "items": [{"exercise_id": row, "sets": [_set()]}]},
    )
    untouched = (await client.get(f"/api/workouts/{original['id']}")).json()
    assert untouched == original


async def test_copy_name_stays_within_limit(client: AsyncClient) -> None:
    await _register(client, "user@example.com")
    original = await _workout(client, "я" * 120, [])

    copy = (await client.post(f"/api/workouts/{original['id']}/copy")).json()
    assert len(copy["name"]) == 120
    assert copy["name"].endswith(" (копия)")


async def test_delete_workout_keeps_exercises(client: AsyncClient) -> None:
    await _register(client, "user@example.com")
    bench = await _exercise(client)
    created = await _workout(client, "День 1", [{"exercise_id": bench, "sets": [_set()]}])

    response = await client.delete(f"/api/workouts/{created['id']}")
    assert response.status_code == 204
    assert (await client.get(f"/api/workouts/{created['id']}")).status_code == 404
    assert (await client.get("/api/exercises")).json()[0]["id"] == bench


async def test_exercise_in_workout_cannot_be_deleted(client: AsyncClient) -> None:
    await _register(client, "user@example.com")
    bench = await _exercise(client)
    created = await _workout(client, "День 1", [{"exercise_id": bench, "sets": [_set()]}])

    response = await client.delete(f"/api/exercises/{bench}")
    assert response.status_code == 409
    assert response.json()["detail"] == (
        "Упражнение входит в тренировки. Сначала уберите его оттуда."
    )
    assert (await client.get(f"/api/exercises/{bench}")).status_code == 200

    # После того как упражнение убрали из тренировки, его можно удалить.
    await client.put(f"/api/workouts/{created['id']}", json={"name": "День 1", "items": []})
    assert (await client.delete(f"/api/exercises/{bench}")).status_code == 204


async def test_workouts_are_isolated_between_users(client: AsyncClient) -> None:
    await _register(client, "first@example.com")
    mine = await _workout(client, "Мой день", [])
    await client.post("/api/auth/logout")

    await _register(client, "second@example.com")
    assert (await client.get("/api/workouts")).json() == []

    workout_id = mine["id"]
    assert (await client.get(f"/api/workouts/{workout_id}")).status_code == 404
    body = {"name": "Чужой", "items": []}
    assert (await client.put(f"/api/workouts/{workout_id}", json=body)).status_code == 404
    assert (
        await client.patch(f"/api/workouts/{workout_id}", json={"name": "Чужой"})
    ).status_code == 404
    assert (await client.post(f"/api/workouts/{workout_id}/copy")).status_code == 404
    assert (await client.delete(f"/api/workouts/{workout_id}")).status_code == 404

    await client.post("/api/auth/logout")
    await client.post(
        "/api/auth/login", json={"email": "first@example.com", "password": "password1"}
    )
    assert (await client.get(f"/api/workouts/{workout_id}")).json()["name"] == "Мой день"


async def test_unknown_workout_returns_404(client: AsyncClient) -> None:
    await _register(client, "user@example.com")
    missing = uuid.uuid4()

    assert (await client.get(f"/api/workouts/{missing}")).status_code == 404
    assert (
        await client.put(f"/api/workouts/{missing}", json={"name": "x", "items": []})
    ).status_code == 404
    assert (await client.delete(f"/api/workouts/{missing}")).status_code == 404


async def test_malformed_workout_id_returns_422(client: AsyncClient) -> None:
    await _register(client, "user@example.com")

    assert (await client.get("/api/workouts/not-a-uuid")).status_code == 422


async def test_validation_rejects_invalid_workouts(client: AsyncClient) -> None:
    await _register(client, "user@example.com")
    bench = await _exercise(client)

    def with_sets(*sets: dict) -> dict:
        return {"name": "День", "items": [{"exercise_id": bench, "sets": list(sets)}]}

    invalid_bodies = [
        {"name": "   ", "items": []},
        {"name": "x" * 121, "items": []},
        {"name": "День", "items": [{"exercise_id": bench, "sets": []}]},
        with_sets(_set(rep_min=0)),
        with_sets(_set(rep_min=13, rep_max=12)),
        with_sets(_set(rep_max=101)),
        with_sets(_set(rir=6)),
        with_sets(_set(rir=-1)),
        with_sets(_set(rest=1801)),
        with_sets(_set(rest=-5)),
        with_sets(*[_set() for _ in range(21)]),
        {
            "name": "День",
            "items": [{"exercise_id": "not-a-uuid", "sets": [_set()]}],
        },
        {"name": "День", "items": [{"exercise_id": bench, "sets": [_set()]}] * 51},
    ]
    for body in invalid_bodies:
        response = await client.post("/api/workouts", json=body)
        assert response.status_code == 422, body
    assert (await client.get("/api/workouts")).json() == []


async def test_optional_rir_and_rest_default_to_none(client: AsyncClient) -> None:
    await _register(client, "user@example.com")
    bench = await _exercise(client)

    created = await _workout(
        client,
        "День",
        [{"exercise_id": bench, "sets": [{"rep_min": 6, "rep_max": 8}]}],
    )
    assert created["items"][0]["sets"][0]["target_rir"] is None
    assert created["items"][0]["sets"][0]["rest_seconds"] is None
