import datetime as dt
import uuid

from app.models.user import User
from app.services.transfer import export_is_due
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from tests.test_log import ASSISTED, BENCH, DUMBBELL, _values

PROFILE = {
    "goal": "cut",
    "height_cm": 180,
    "age": 32,
    "sex": "male",
    "weight_unit": "kg",
    "theme": "dark",
}


def test_export_reminder_waits_a_month_and_resets_after_export() -> None:
    created = dt.datetime(2026, 1, 1, tzinfo=dt.UTC)
    assert export_is_due(created, None, created + dt.timedelta(days=29)) is False
    assert export_is_due(created, None, created + dt.timedelta(days=30)) is True
    exported = created + dt.timedelta(days=40)
    assert export_is_due(created, exported, exported + dt.timedelta(days=29)) is False
    assert export_is_due(created, exported, exported + dt.timedelta(days=30)) is True


async def _register(client: AsyncClient, email: str) -> None:
    response = await client.post(
        "/api/auth/register", json={"email": email, "password": "password1"}
    )
    assert response.status_code == 201


async def _login(client: AsyncClient, email: str) -> None:
    response = await client.post(
        "/api/auth/login", json={"email": email, "password": "password1"}
    )
    assert response.status_code == 200


def _without_ids(row: dict, drop: set[str]) -> dict:
    return {key: value for key, value in row.items() if key not in drop}


def fingerprint(document: dict) -> dict:
    """Сравнивает содержимое, а не идентификаторы: после импорта они новые."""
    exercise_names = {row["id"]: row["name"] for row in document["exercises"]}
    template_names = {row["id"]: row["name"] for row in document["workout_templates"]}
    planned_keys = {
        row["id"]: (row["date"], row["position"], row["name"])
        for row in document["planned_workouts"]
    }

    def exercise_name(exercise_id: str | None) -> str | None:
        if exercise_id is None:
            return None
        return exercise_names.get(exercise_id, f"missing:{exercise_id}")

    exercises = sorted(
        (_without_ids(row, {"id"}) for row in document["exercises"]),
        key=lambda row: (row["name"], row["archived"]),
    )
    templates = []
    for row in document["workout_templates"]:
        items = []
        for item in sorted(row["items"], key=lambda item: item["position"]):
            sets = [
                _without_ids(set_, {"id"})
                for set_ in sorted(item["sets"], key=lambda set_: set_["position"])
            ]
            items.append(
                {
                    "position": item["position"],
                    "exercise": exercise_name(item["exercise_id"]),
                    "sets": sets,
                }
            )
        templates.append({"name": row["name"], "created_at": row["created_at"], "items": items})

    planned = []
    for row in document["planned_workouts"]:
        snapshot = []
        for item in row["snapshot"]:
            exercise = dict(item["exercise"])
            exercise["exercise_id"] = exercise_name(exercise["exercise_id"])
            snapshot.append({**item, "exercise": exercise})
        planned.append(
            {
                **_without_ids(row, {"id"}),
                "template_id": None
                if row["template_id"] is None
                else template_names[row["template_id"]],
                "snapshot": snapshot,
            }
        )

    logs = []
    for row in document["plan_change_logs"]:
        changes = [
            {**change, "id": planned_keys[change["id"]]} for change in row["payload"]["changes"]
        ]
        logs.append(
            {
                "operation": row["operation"],
                "created_at": row["created_at"],
                "payload": {**row["payload"], "changes": changes},
            }
        )

    performed = []
    for row in document["performed_workouts"]:
        items = []
        for item in sorted(row["items"], key=lambda item: item["position"]):
            sets = []
            for logged in sorted(item["sets"], key=lambda logged: logged["position"]):
                sets.append(
                    {
                        **_without_ids(logged, {"id"}),
                        "exercise_id": exercise_name(logged["exercise_id"]),
                    }
                )
            items.append(
                {
                    **_without_ids(item, {"id"}),
                    "exercise_id": exercise_name(item["exercise_id"]),
                    "sets": sets,
                }
            )
        performed.append(
            {
                **_without_ids(row, {"id"}),
                "planned_id": None
                if row["planned_id"] is None
                else planned_keys[row["planned_id"]],
                "items": items,
            }
        )

    performed_keys = {
        row["id"]: (row["date"], row["started_at"]) for row in document["performed_workouts"]
    }
    decisions = [
        {
            "exercise": exercise_name(row["exercise_id"]),
            "status": row["status"],
            "session": performed_keys[row["last_session_id"]],
            "suggested_weight": row["suggested_weight"],
            "action": row["action"],
        }
        for row in document.get("progression_decisions", [])
    ]
    decisions.sort(key=lambda row: (row["exercise"] or "", str(row["session"]), row["action"]))

    return {
        "profile": document["profile"],
        "exercises": exercises,
        "workout_templates": templates,
        "planned_workouts": planned,
        "plan_change_logs": logs,
        "performed_workouts": performed,
        "progression_decisions": decisions,
    }


async def test_export_requires_login(client: AsyncClient) -> None:
    assert (await client.get("/api/export")).status_code == 401
    assert (await client.get("/api/export/workouts.csv")).status_code == 401
    rejected = await client.post("/api/import", params={"mode": "replace"}, json={})
    assert rejected.status_code == 401


async def test_roundtrip_replaces_account_and_keeps_owner_data(client: AsyncClient) -> None:
    await _register(client, "owner@example.com")
    saved = await client.put("/api/profile", json=PROFILE)
    assert saved.status_code == 200, saved.text

    bench = await client.post("/api/exercises", json=BENCH)
    dumbbell = await client.post("/api/exercises", json=DUMBBELL)
    assisted = await client.post("/api/exercises", json=ASSISTED)
    assert bench.status_code == assisted.status_code == 201
    archived = await client.post(f"/api/exercises/{assisted.json()['id']}/archive")
    assert archived.status_code == 200

    template = await client.post(
        "/api/workouts",
        json={
            "name": "День A",
            "items": [
                {
                    "exercise_id": bench.json()["id"],
                    "sets": [
                        {"rep_min": 8, "rep_max": 12, "target_rir": 2, "rest_seconds": 90},
                        {"rep_min": 6, "rep_max": 8, "target_rir": 1, "rest_seconds": 120},
                    ],
                },
                {
                    "exercise_id": dumbbell.json()["id"],
                    "sets": [{"rep_min": 10, "rep_max": 15, "target_rir": 3, "rest_seconds": 60}],
                },
            ],
        },
    )
    assert template.status_code == 201, template.text
    entry = await client.post(
        "/api/plan/entries",
        json={"date": "2026-11-10", "template_id": template.json()["id"]},
    )
    rest = await client.post("/api/plan/entries", json={"date": "2026-11-12", "kind": "rest"})
    assert entry.status_code == rest.status_code == 201

    shifted = await client.post(
        "/api/plan/shift/apply",
        json={"operation": "shift_only", "entry_id": entry.json()["id"], "days": 1},
    )
    assert shifted.status_code == 200, shifted.text

    started = await client.post("/api/performed", json={"planned_id": entry.json()["id"]})
    assert started.status_code == 201, started.text
    workout = started.json()
    first_set = workout["items"][0]["sets"][0]
    saved_set = await client.put(
        f"/api/performed/{workout['id']}/sets/{first_set['id']}",
        json=_values(weight=80, extra_weight=2.5, reps=12, rir=2, note="узкий хват"),
    )
    assert saved_set.status_code == 200, saved_set.text
    finished = await client.post(f"/api/performed/{workout['id']}/finish")
    assert finished.status_code == 200, finished.text
    bench_id = bench.json()["id"]
    hint = await client.get(f"/api/progression/{bench_id}")
    assert hint.status_code == 200, hint.text
    assert hint.json()["status"] == "increase_weight"
    rejected = await client.post(
        f"/api/progression/{bench_id}/decision", json={"action": "reject"}
    )
    assert rejected.status_code == 200, rejected.text

    exported = await client.get("/api/export")
    assert exported.status_code == 200, exported.text
    original = exported.json()
    assert original["format_version"] == 1
    assert original["profile"] == PROFILE
    assert len(original["plan_change_logs"]) == 1
    assert len(original["progression_decisions"]) == 1
    assert original["progression_decisions"][0]["action"] == "reject"

    table = await client.get("/api/export/workouts.csv")
    assert table.status_code == 200
    assert "text/csv" in table.headers["content-type"]
    text = table.content.decode("utf-8-sig")
    assert "Жим штанги лёжа" in text
    assert "80" in text
    assert "узкий хват" in text

    await client.post("/api/auth/logout")
    await _register(client, "other@example.com")
    leftover = await client.post("/api/exercises", json={**BENCH, "name": "Чужое"})
    assert leftover.status_code == 201

    imported = await client.post("/api/import", params={"mode": "replace"}, json=original)
    assert imported.status_code == 200, imported.text
    assert imported.json()["exercises"] == 3
    assert imported.json()["performed_workouts"] == 1

    copied = await client.get("/api/export")
    assert copied.status_code == 200, copied.text
    copy = copied.json()
    assert fingerprint(original) == fingerprint(copy)
    assert {row["id"] for row in original["exercises"]}.isdisjoint(
        {row["id"] for row in copy["exercises"]}
    )
    names = {row["name"] for row in copy["exercises"]}
    assert "Чужое" not in names
    archived = {row["name"] for row in copy["exercises"] if row["archived"]}
    assert archived == {"Подтягивания в гравитроне"}
    copied_bench = next(row["id"] for row in copy["exercises"] if row["name"] == "Жим штанги лёжа")
    hidden = await client.get(f"/api/progression/{copied_bench}")
    assert hidden.status_code == 200
    assert hidden.json() is None

    undone = await client.post("/api/plan/shift/undo")
    assert undone.status_code == 200, undone.text
    plan = await client.get("/api/plan", params={"start": "2026-11-01", "end": "2026-11-30"})
    dates = {row["name"]: row["date"] for row in plan.json() if row["kind"] == "workout"}
    assert dates["День A"] == "2026-11-10"

    await client.post("/api/auth/logout")
    await _login(client, "owner@example.com")
    owner_again = await client.get("/api/export")
    assert owner_again.status_code == 200
    again = owner_again.json()
    assert fingerprint(again) == fingerprint(original)
    assert {row["id"] for row in again["exercises"]} == {row["id"] for row in original["exercises"]}
    owner_day = next(row["date"] for row in again["planned_workouts"] if row["name"] == "День A")
    assert owner_day == "2026-11-11"


async def test_invalid_import_leaves_data_in_place(client: AsyncClient) -> None:
    await _register(client, "keep@example.com")
    created = await client.post("/api/exercises", json=BENCH)
    assert created.status_code == 201
    exported = await client.get("/api/export")
    assert exported.status_code == 200
    broken = exported.json()
    broken["workout_templates"] = [
        {
            "id": str(uuid.uuid4()),
            "name": "Битая ссылка",
            "created_at": "2026-11-01T00:00:00Z",
            "items": [
                {
                    "id": str(uuid.uuid4()),
                    "exercise_id": str(uuid.uuid4()),
                    "position": 0,
                    "sets": [
                        {
                            "id": str(uuid.uuid4()),
                            "position": 0,
                            "rep_min": 8,
                            "rep_max": 12,
                            "target_rir": 2,
                            "rest_seconds": 90,
                        }
                    ],
                }
            ],
        }
    ]

    rejected = await client.post("/api/import", params={"mode": "replace"}, json=broken)
    assert rejected.status_code == 422

    unknown = dict(exported.json())
    unknown["format_version"] = 99
    rejected_version = await client.post(
        "/api/import", params={"mode": "replace"}, json=unknown
    )
    assert rejected_version.status_code == 422
    missing_mode = await client.post("/api/import", json=exported.json())
    assert missing_mode.status_code == 422

    listed = await client.get("/api/exercises")
    assert listed.status_code == 200
    assert [row["id"] for row in listed.json()] == [created.json()["id"]]


async def test_today_asks_for_export_after_a_month(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _register(client, "old@example.com")
    fresh = await client.get("/api/today", params={"day": "2026-11-07"})
    assert fresh.status_code == 200
    assert fresh.json()["export_reminder"] is False

    me = await client.get("/api/auth/me")
    user = await db_session.get(User, uuid.UUID(me.json()["id"]))
    assert user is not None
    user.created_at = dt.datetime.now(dt.UTC) - dt.timedelta(days=40)
    await db_session.commit()

    due = await client.get("/api/today", params={"day": "2026-11-07"})
    assert due.json()["export_reminder"] is True

    exported = await client.get("/api/export")
    assert exported.status_code == 200
    quiet = await client.get("/api/today", params={"day": "2026-11-07"})
    assert quiet.json()["export_reminder"] is False
