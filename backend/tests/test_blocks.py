"""API блоков периодизации: библиотека, применение с датой старта и сдвиг границ."""

from typing import Any

from app.models.plan import PlannedWorkout
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from tests.schema_setup import run_alembic

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
        "/api/auth/register", json={"email": email, "password": "password1"}
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
                    "sets": [
                        {"rep_min": 8, "rep_max": 12, "target_rir": 2, "rest_seconds": 90},
                        {"rep_min": 8, "rep_max": 12, "target_rir": 2, "rest_seconds": 90},
                    ],
                }
            ],
        },
    )
    assert created.status_code == 201, created.text
    return created.json()["id"]


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


def _block_body(name: str, weeks: list[dict[str, Any]], schedule: list[dict[str, Any]]) -> dict:
    return {"name": name, "weeks": weeks, "schedule": schedule}


async def _block(client: AsyncClient, template_a: str, template_b: str) -> dict:
    """Два недели: день 0 — тренировка A, день 2 — отдых, день 4 — тренировка B."""
    body = _block_body(
        "Гипертрофия",
        [
            _week(),
            _week("deload", rep_min=3, rep_max=5, rir=0, volume=0.5),
        ],
        [
            {"day_index": 0, "kind": "workout", "template_id": template_a},
            {"day_index": 2, "kind": "rest"},
            {"day_index": 4, "kind": "workout", "template_id": template_b},
        ],
    )
    created = await client.post("/api/blocks", json=body)
    assert created.status_code == 201, created.text
    return created.json()


async def _plan(client: AsyncClient) -> list[dict]:
    response = await client.get("/api/plan", params={"start": "2026-11-01", "end": "2026-11-30"})
    assert response.status_code == 200, response.text
    return response.json()


def _on(entries: list[dict], day: str) -> dict:
    [entry] = [entry for entry in entries if entry["date"] == day]
    return entry


async def _apply(client: AsyncClient, block_id: str, start: str = "2026-11-02") -> dict:
    applied = await client.post(f"/api/blocks/{block_id}/apply", json={"start_date": start})
    assert applied.status_code == 201, applied.text
    return applied.json()


async def _open_rows(db: AsyncSession) -> int:
    return int(
        await db.scalar(
            select(func.count())
            .select_from(PlannedWorkout)
            .where(PlannedWorkout.placement_id.is_not(None))
        )
        or 0
    )


async def test_blocks_require_login(client: AsyncClient) -> None:
    assert (await client.get("/api/blocks")).status_code == 401
    assert (await client.post("/api/blocks", json={})).status_code == 401
    assert (await client.get("/api/blocks/placements")).status_code == 401


async def test_create_list_get_and_replace_a_block(client: AsyncClient) -> None:
    await _register(client, "user@example.com")
    template_a = await _template(client, "День A")
    template_b = await _template(client, "День B")

    block = await _block(client, template_a, template_b)
    assert block["length_weeks"] == 2
    assert block["cycle_days"] == 7
    assert [week["position"] for week in block["weeks"]] == [1, 2]
    assert [item["kind"] for item in block["schedule"]] == ["workout", "rest", "workout"]
    assert block["schedule"][0]["name"] == "День A"

    listed = (await client.get("/api/blocks")).json()
    assert [item["id"] for item in listed] == [block["id"]]
    assert (await client.get(f"/api/blocks/{block['id']}")).json()["name"] == "Гипертрофия"

    replaced = await client.put(
        f"/api/blocks/{block['id']}",
        json=_block_body(
            "Силовая",
            [_week("strength", rep_min=3, rep_max=5, rir=1)],
            [{"day_index": 1, "kind": "workout", "template_id": template_b}],
        ),
    )
    assert replaced.status_code == 200, replaced.text
    assert replaced.json()["length_weeks"] == 1
    assert replaced.json()["name"] == "Силовая"
    assert [item["day_index"] for item in replaced.json()["schedule"]] == [1]


async def test_invalid_block_bodies_are_rejected(client: AsyncClient) -> None:
    await _register(client, "user@example.com")
    template = await _template(client, "День A")

    reversed_reps = _block_body(
        "Ошибка",
        [_week(rep_min=10, rep_max=8)],
        [{"day_index": 0, "kind": "workout", "template_id": template}],
    )
    assert (await client.post("/api/blocks", json=reversed_reps)).status_code == 422

    only_rest = _block_body("Ошибка", [_week()], [{"day_index": 0, "kind": "rest"}])
    assert (await client.post("/api/blocks", json=only_rest)).status_code == 422

    duplicate_day = _block_body(
        "Ошибка",
        [_week()],
        [
            {"day_index": 0, "kind": "workout", "template_id": template},
            {"day_index": 0, "kind": "rest"},
        ],
    )
    assert (await client.post("/api/blocks", json=duplicate_day)).status_code == 422

    beyond_cycle = _block_body(
        "Ошибка",
        [_week()],
        [{"day_index": 5, "kind": "workout", "template_id": template}],
    )
    beyond_cycle["cycle_days"] = 5
    assert (await client.post("/api/blocks", json=beyond_cycle)).status_code == 422

    foreign_template = _block_body(
        "Ошибка",
        [_week()],
        [
            {
                "day_index": 0,
                "kind": "workout",
                "template_id": "00000000-0000-0000-0000-000000000009",
            }
        ],
    )
    refused = await client.post("/api/blocks", json=foreign_template)
    assert refused.status_code == 422
    assert (await client.get("/api/blocks")).json() == []


async def test_blocks_belong_to_their_owner(client: AsyncClient) -> None:
    await _register(client, "user@example.com")
    template = await _template(client, "День A")
    block = await _block(client, template, template)
    applied = await _apply(client, block["id"])

    assert (await client.post("/api/auth/logout")).status_code == 204
    await _register(client, "other@example.com")
    assert (await client.get(f"/api/blocks/{block['id']}")).status_code == 404
    assert (
        await client.put(
            f"/api/blocks/{block['id']}",
            json=_block_body(
                "Чужой",
                [_week()],
                [{"day_index": 0, "kind": "workout", "template_id": template}],
            ),
        )
    ).status_code == 404
    assert (await client.delete(f"/api/blocks/{block['id']}")).status_code == 404
    assert (await client.post(f"/api/blocks/{block['id']}/copy")).status_code == 404
    assert (
        await client.post(f"/api/blocks/{block['id']}/apply", json={"start_date": "2026-11-02"})
    ).status_code == 404
    assert (await client.delete(f"/api/blocks/placements/{applied['id']}")).status_code == 404
    assert (await client.get("/api/blocks/placements")).json() == []


async def test_copy_is_an_independent_library_entry(client: AsyncClient) -> None:
    await _register(client, "user@example.com")
    template = await _template(client, "День A")
    original = await _block(client, template, template)

    copied = await client.post(f"/api/blocks/{original['id']}/copy")
    assert copied.status_code == 201, copied.text
    assert copied.json()["name"] == "Гипертрофия (копия)"
    assert copied.json()["weeks"] == original["weeks"]
    assert copied.json()["schedule"] == original["schedule"]

    await client.delete(f"/api/blocks/{copied.json()['id']}")
    assert (await client.get(f"/api/blocks/{original['id']}")).status_code == 200


async def test_apply_creates_the_schedule_from_the_start_date(client: AsyncClient) -> None:
    await _register(client, "user@example.com")
    template_a = await _template(client, "День A")
    template_b = await _template(client, "День B")
    block = await _block(client, template_a, template_b)

    placement = await _apply(client, block["id"])
    assert placement["start_date"] == "2026-11-02"
    assert placement["end_date"] == "2026-11-15"
    assert placement["block_id"] == block["id"]

    entries = await _plan(client)
    assert [(entry["date"], entry["kind"]) for entry in entries] == [
        ("2026-11-02", "workout"),
        ("2026-11-04", "rest"),
        ("2026-11-06", "workout"),
        ("2026-11-09", "workout"),
        ("2026-11-11", "rest"),
        ("2026-11-13", "workout"),
    ]
    first = _on(entries, "2026-11-02")
    assert first["name"] == "День A"
    assert first["status"] == "planned"
    assert first["placement_id"] == placement["id"]
    assert first["items"][0]["sets"][0]["rep_min"] == 8
    assert first["items"][0]["sets"][0]["target_rir"] == 2
    # Вторая неделя: диапазон 3–5, RIR 0, половина подходов (из двух осталось один).
    deload = _on(entries, "2026-11-09")
    assert deload["items"][0]["sets"][0]["rep_min"] == 3
    assert deload["items"][0]["sets"][0]["target_rir"] == 0
    assert len(deload["items"][0]["sets"]) == 1
    assert _on(entries, "2026-11-04")["name"] is None

    assert [item["id"] for item in (await client.get("/api/blocks/placements")).json()] == [
        placement["id"]
    ]


async def test_apply_refuses_busy_days_and_leaves_no_placement(client: AsyncClient) -> None:
    await _register(client, "user@example.com")
    template = await _template(client, "День A")
    block = await _block(client, template, template)
    await client.post("/api/plan/entries", json={"date": "2026-11-09", "name": "Свой день"})

    refused = await client.post(
        f"/api/blocks/{block['id']}/apply", json={"start_date": "2026-11-02"}
    )
    assert refused.status_code == 409
    assert "2026-11-09" in refused.json()["detail"]
    assert (await client.get("/api/blocks/placements")).json() == []


async def test_editing_a_template_does_not_change_the_applied_block(client: AsyncClient) -> None:
    await _register(client, "user@example.com")
    template = await _template(client, "День A")
    block = await _block(client, template, template)
    await _apply(client, block["id"])
    before = _on(await _plan(client), "2026-11-02")["items"]

    exercise_id = (await client.get("/api/exercises")).json()[0]["id"]
    edited = await client.put(
        f"/api/workouts/{template}",
        json={
            "name": "День A (правка)",
            "items": [
                {
                    "exercise_id": exercise_id,
                    "sets": [{"rep_min": 1, "rep_max": 2, "target_rir": 0, "rest_seconds": None}],
                }
            ],
        },
    )
    assert edited.status_code == 200, edited.text

    after = _on(await _plan(client), "2026-11-02")
    assert after["items"] == before
    assert after["name"] == "День A"


async def test_changing_one_block_day_stores_only_that_day(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _register(client, "user@example.com")
    template = await _template(client, "День A")
    block = await _block(client, template, template)
    await _apply(client, block["id"])
    first = _on(await _plan(client), "2026-11-02")

    done = await client.patch(f"/api/plan/{first['id']}", json={"status": "done"})
    assert done.status_code == 200, done.text
    assert await _open_rows(db_session) == 1

    entries = await _plan(client)
    assert _on(entries, "2026-11-02")["status"] == "done"
    assert _on(entries, "2026-11-09")["status"] == "planned"
    assert len(entries) == 6

    refused = await client.delete(f"/api/plan/{first['id']}")
    assert refused.status_code == 409


async def test_shift_from_block_start_moves_the_block_without_rows(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _register(client, "user@example.com")
    template = await _template(client, "День A")
    block = await _block(client, template, template)
    placement = await _apply(client, block["id"])
    first = _on(await _plan(client), "2026-11-02")
    body = {
        "operation": "shift_following",
        "entry_id": first["id"],
        "days": 1,
        "resolution": "cascade",
    }

    preview = await client.post("/api/plan/shift/preview", json=body)
    assert preview.status_code == 200, preview.text
    [moved] = preview.json()["blocks"]
    assert (moved["start_after"], moved["end_after"]) == ("2026-11-03", "2026-11-16")

    applied = await client.post("/api/plan/shift/apply", json=body)
    assert applied.status_code == 200, applied.text
    assert await _open_rows(db_session) == 0

    placements = (await client.get("/api/blocks/placements")).json()
    assert (placements[0]["start_date"], placements[0]["end_date"]) == ("2026-11-03", "2026-11-16")
    assert placements[0]["id"] == placement["id"]
    assert _on(await _plan(client), "2026-11-03")["name"] == "День A"

    undo = await client.post("/api/plan/shift/undo")
    assert undo.status_code == 200, undo.text
    assert (await client.get("/api/blocks/placements")).json()[0]["start_date"] == "2026-11-02"


async def test_shift_inside_block_stores_moved_days_and_undo_restores_them(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _register(client, "user@example.com")
    template = await _template(client, "День A")
    block = await _block(client, template, template)
    await _apply(client, block["id"])
    second_week = _on(await _plan(client), "2026-11-09")
    body = {
        "operation": "shift_following",
        "entry_id": second_week["id"],
        "days": 2,
        "resolution": "cascade",
    }

    applied = await client.post("/api/plan/shift/apply", json=body)
    assert applied.status_code == 200, applied.text
    assert await _open_rows(db_session) == 3

    placements = (await client.get("/api/blocks/placements")).json()
    assert (placements[0]["start_date"], placements[0]["end_date"]) == ("2026-11-02", "2026-11-17")
    entries = await _plan(client)
    assert _on(entries, "2026-11-11")["kind"] == "workout"
    assert _on(entries, "2026-11-13")["kind"] == "rest"
    assert _on(entries, "2026-11-15")["name"] == "День A"

    undo = await client.post("/api/plan/shift/undo")
    assert undo.status_code == 200, undo.text
    assert await _open_rows(db_session) == 0
    assert (await client.get("/api/blocks/placements")).json()[0]["end_date"] == "2026-11-15"
    assert _on(await _plan(client), "2026-11-09")["status"] == "planned"


async def test_removing_a_placement_drops_open_days_and_keeps_history(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _register(client, "user@example.com")
    template = await _template(client, "День A")
    block = await _block(client, template, template)
    placement = await _apply(client, block["id"])
    first = _on(await _plan(client), "2026-11-02")
    assert (
        await client.patch(f"/api/plan/{first['id']}", json={"status": "done"})
    ).status_code == 200

    removed = await client.delete(f"/api/blocks/placements/{placement['id']}")
    assert removed.status_code == 204, removed.text

    entries = await _plan(client)
    assert [entry["date"] for entry in entries] == ["2026-11-02"]
    assert entries[0]["status"] == "done"
    assert entries[0]["placement_id"] is None
    assert (await client.get(f"/api/blocks/{block['id']}")).status_code == 200


async def test_block_deletion_keeps_applied_placements(client: AsyncClient) -> None:
    await _register(client, "user@example.com")
    template = await _template(client, "День A")
    block = await _block(client, template, template)
    await _apply(client, block["id"])

    assert (await client.delete(f"/api/blocks/{block['id']}")).status_code == 204
    placements = (await client.get("/api/blocks/placements")).json()
    assert placements[0]["block_id"] is None
    assert len(await _plan(client)) == 6


async def test_repeating_block_continues_the_cycle_after_the_last_week(client: AsyncClient) -> None:
    await _register(client, "user@example.com")
    template_a = await _template(client, "День A")
    template_b = await _template(client, "День B")
    block = await _block(client, template_a, template_b)

    applied = await client.post(
        f"/api/blocks/{block['id']}/apply",
        json={"start_date": "2026-11-02", "repeats": True},
    )
    assert applied.status_code == 201, applied.text
    assert applied.json()["repeats"] is True
    assert applied.json()["end_date"] is None

    entries = await _plan(client)
    assert _on(entries, "2026-11-09")["items"][0]["sets"][0]["rep_min"] == 3
    again = _on(entries, "2026-11-16")
    assert again["name"] == "День A"
    assert again["items"][0]["sets"][0]["rep_min"] == 8


async def test_repeat_extends_a_block_already_on_the_calendar(client: AsyncClient) -> None:
    await _register(client, "user@example.com")
    template = await _template(client, "День A")
    block = await _block(client, template, template)
    placement = await _apply(client, block["id"])
    assert all(entry["date"] <= "2026-11-15" for entry in await _plan(client))

    extended = await client.post(f"/api/blocks/placements/{placement['id']}/repeat")
    assert extended.status_code == 200, extended.text
    assert extended.json()["end_date"] is None
    assert _on(await _plan(client), "2026-11-16")["name"] == "День A"


async def test_block_migration_can_be_reverted_and_reapplied() -> None:
    run_alembic("downgrade", "0011")
    run_alembic("upgrade", "head")
    run_alembic("check")
