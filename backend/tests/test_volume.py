from httpx import AsyncClient
from tests.test_log import (
    ASSISTED,
    BENCH,
    _exercise,
    _plan_workout,
    _register,
    _start,
    _values,
)

VOLUME = "/api/volume/muscles"


async def _log(client: AsyncClient, exercise_id: str, day: str, sets: list[dict]) -> dict:
    """План на день, старт и запись подходов. Подходы сверх двух из шаблона добавляются."""
    planned = await _plan_workout(client, exercise_id, day)
    _, workout = await _start(client, planned["id"])
    item = workout["items"][0]
    for logged, body in zip(item["sets"], sets, strict=False):
        saved = await client.put(
            f"/api/performed/{workout['id']}/sets/{logged['id']}",
            json=_values(**body),
        )
        assert saved.status_code == 200, saved.text
    for body in sets[len(item["sets"]) :]:
        created = await client.post(
            f"/api/performed/{workout['id']}/items/{item['id']}/sets",
            json=_values(**body),
        )
        assert created.status_code == 201, created.text
    return workout


def _groups(body: dict) -> dict[str | None, int]:
    return {group["muscle"]: group["sets"] for group in body["groups"]}


async def test_volume_requires_login(client: AsyncClient) -> None:
    response = await client.get(VOLUME, params={"day": "2026-11-04"})
    assert response.status_code == 401


async def test_week_is_monday_to_sunday(client: AsyncClient) -> None:
    await _register(client, "week@example.com")
    exercise_id = await _exercise(client, BENCH)
    # 2026-11-02 — понедельник, 2026-11-08 — воскресенье, 2026-11-09 — следующий понедельник.
    await _log(client, exercise_id, "2026-11-02", [{"weight": 60, "reps": 8}])
    await _log(client, exercise_id, "2026-11-08", [{"weight": 60, "reps": 8}])
    await _log(client, exercise_id, "2026-11-09", [{"weight": 60, "reps": 8}])

    for day in ("2026-11-02", "2026-11-05", "2026-11-08"):
        response = await client.get(VOLUME, params={"day": day})
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["week_start"] == "2026-11-02"
        assert body["week_end"] == "2026-11-08"
        assert _groups(body) == {"chest": 2}

    next_week = await client.get(VOLUME, params={"day": "2026-11-09"})
    assert next_week.json()["week_start"] == "2026-11-09"
    assert next_week.json()["week_end"] == "2026-11-15"
    assert _groups(next_week.json()) == {"chest": 1}


async def test_warmup_and_empty_sets_are_not_counted(client: AsyncClient) -> None:
    await _register(client, "warmup@example.com")
    exercise_id = await _exercise(client, BENCH)
    await _log(
        client,
        exercise_id,
        "2026-11-04",
        [
            {"weight": 20, "reps": 12, "is_warmup": True},
            {"weight": 60, "reps": 8},
            {"weight": 60, "reps": None},
            {"weight": 70, "reps": 6},
        ],
    )

    body = (await client.get(VOLUME, params={"day": "2026-11-04"})).json()
    assert _groups(body) == {"chest": 2}


async def test_assisted_and_negative_sets_are_counted(client: AsyncClient) -> None:
    await _register(client, "assisted@example.com")
    back_id = await _exercise(client, ASSISTED)
    await _log(
        client,
        back_id,
        "2026-11-04",
        [
            {"weight": 20, "reps": 8, "is_assisted": True},
            {"reps": 4, "is_negative": True},
            {"weight": 10, "reps": 10},
        ],
    )

    body = (await client.get(VOLUME, params={"day": "2026-11-04"})).json()
    assert _groups(body) == {"back": 3}


async def test_secondary_muscle_gets_no_set(client: AsyncClient) -> None:
    await _register(client, "secondary@example.com")
    # У жима вторичная группа — трицепс. Подход идёт только в грудь.
    exercise_id = await _exercise(client, BENCH)
    await _log(client, exercise_id, "2026-11-04", [{"weight": 60, "reps": 8}])

    body = (await client.get(VOLUME, params={"day": "2026-11-04"})).json()
    assert _groups(body) == {"chest": 1}
    assert "triceps" not in _groups(body)


async def test_deleted_exercise_goes_to_no_group(client: AsyncClient) -> None:
    await _register(client, "deleted@example.com")
    exercise_id = await _exercise(client, BENCH)
    planned = await _plan_workout(client, exercise_id, "2026-11-04")
    _, workout = await _start(client, planned["id"])
    item = workout["items"][0]
    for logged in item["sets"]:
        saved = await client.put(
            f"/api/performed/{workout['id']}/sets/{logged['id']}",
            json=_values(weight=60, reps=8),
        )
        assert saved.status_code == 200, saved.text

    # Снимаем упражнение с плана и из шаблона, затем удаляем из справочника.
    assert (await client.delete(f"/api/plan/{planned['id']}")).status_code == 204
    template_id = planned["template_id"]
    assert (await client.delete(f"/api/workouts/{template_id}")).status_code == 204
    deleted = await client.delete(f"/api/exercises/{exercise_id}")
    assert deleted.status_code == 204, deleted.text

    body = (await client.get(VOLUME, params={"day": "2026-11-04"})).json()
    assert body["groups"] == [
        {"muscle": None, "sets": 2, "target_min": None, "target_max": None, "status": None}
    ]


async def test_other_users_sets_are_not_visible(client: AsyncClient) -> None:
    await _register(client, "owner-volume@example.com")
    exercise_id = await _exercise(client, BENCH)
    await _log(client, exercise_id, "2026-11-04", [{"weight": 60, "reps": 8}] * 3)
    await client.post("/api/auth/logout")

    await _register(client, "other-volume@example.com")
    body = (await client.get(VOLUME, params={"day": "2026-11-04"})).json()
    assert body["groups"] == []
    assert body["week_start"] == "2026-11-02"


async def test_empty_week_has_no_groups(client: AsyncClient) -> None:
    await _register(client, "empty-volume@example.com")
    response = await client.get(VOLUME, params={"day": "2026-11-04"})
    assert response.status_code == 200
    assert response.json()["groups"] == []
