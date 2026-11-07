from app.models.inbody import InbodyScan
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

SCAN = {
    "measured_on": "2026-10-26",
    "measured_time": "08:30:00",
    "weight_kg": 84.7,
    "smm_kg": 43,
    "bfm_kg": 9.9,
    "pbf_percent": 11.7,
    "tbw_l": 54.8,
    "visceral_fat_level": 3,
    "bmr_kcal": 1985,
}


async def _register(client: AsyncClient, email: str) -> None:
    response = await client.post(
        "/api/auth/register",
        json={"email": email, "password": "password1"},
    )
    assert response.status_code == 201


def _sheet_pdf(lines: list[str]) -> bytes:
    commands = ["BT", "/F1 11 Tf", "40 780 Td"]
    for index, line in enumerate(lines):
        escaped = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        if index:
            commands.append("0 -14 Td")
        commands.append(f"({escaped}) Tj")
    commands.append("ET")
    stream = "\n".join(commands).encode("ascii")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>"
        ),
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    parts = [b"%PDF-1.4\n"]
    offsets = [0]
    for number, body in enumerate(objects, start=1):
        offsets.append(sum(len(part) for part in parts))
        parts.append(f"{number} 0 obj\n".encode() + body + b"\nendobj\n")
    xref_at = sum(len(part) for part in parts)
    xref = [f"xref\n0 {len(objects) + 1}\n".encode(), b"0000000000 65535 f \n"]
    xref.extend(f"{offset:010d} 00000 n \n".encode() for offset in offsets[1:])
    parts.append(b"".join(xref))
    trailer = f"trailer << /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_at}\n%%EOF\n"
    parts.append(trailer.encode())
    return b"".join(parts)


async def test_inbody_requires_login(client: AsyncClient) -> None:
    assert (await client.get("/api/inbody")).status_code == 401
    assert (await client.post("/api/inbody", json=SCAN)).status_code == 401
    assert (await client.post("/api/inbody/parse")).status_code == 401


async def test_owner_creates_compares_and_deletes(client: AsyncClient) -> None:
    await _register(client, "owner@example.com")

    created = await client.post("/api/inbody", json=SCAN)
    assert created.status_code == 201, created.text
    first = created.json()
    assert first["deltas"] == []
    assert first["weight_kg"] == 84.7

    second_body = {
        **SCAN,
        "measured_on": "2026-11-09",
        "weight_kg": 85.1,
        "pbf_percent": 12,
        "visceral_fat_level": 4,
    }
    second = await client.post("/api/inbody", json=second_body)
    assert second.status_code == 201, second.text
    body = second.json()
    deltas = {row["code"]: row for row in body["deltas"]}
    assert deltas["weight_kg"]["absolute"] == 0.4
    assert deltas["weight_kg"]["relative_percent"] == 0.5
    assert deltas["pbf_percent"]["unit"] == "pp"
    assert deltas["pbf_percent"]["absolute"] == 0.3
    assert deltas["visceral_fat_level"]["unit"] == "level"
    assert deltas["visceral_fat_level"]["absolute"] == 1

    listed = await client.get("/api/inbody")
    assert listed.status_code == 200
    assert [row["measured_on"] for row in listed.json()] == ["2026-10-26", "2026-11-09"]

    edited = await client.put(
        f"/api/inbody/{body['id']}",
        json={**second_body, "weight_kg": 85},
    )
    assert edited.status_code == 200, edited.text
    assert edited.json()["weight_kg"] == 85

    removed = await client.delete(f"/api/inbody/{body['id']}")
    assert removed.status_code == 204
    left = await client.get("/api/inbody")
    assert [row["id"] for row in left.json()] == [first["id"]]


async def test_other_user_gets_404_and_does_not_see_scans(client: AsyncClient) -> None:
    await _register(client, "owner@example.com")
    created = await client.post("/api/inbody", json=SCAN)
    scan_id = created.json()["id"]
    await client.post("/api/auth/logout")

    await _register(client, "other@example.com")
    hidden = await client.get("/api/inbody")
    assert hidden.status_code == 200
    assert hidden.json() == []
    assert (await client.put(f"/api/inbody/{scan_id}", json=SCAN)).status_code == 404
    assert (await client.delete(f"/api/inbody/{scan_id}")).status_code == 404


async def test_pdf_parse_returns_numbers_and_does_not_store_a_scan(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _register(client, "owner@example.com")
    pdf = _sheet_pdf(
        [
            "Test Date / Time 2026.11.07. 09:15",
            "Total Body Water (L) 48.5",
            "Body Fat Mass (kg) 16.4",
            "Weight (kg) 84.7",
            "Skeletal Muscle Mass (kg) 38.2",
            "PBF (%) 19.4",
            "Visceral Fat Level 7",
            "Basal Metabolic Rate 1750 kcal",
        ]
    )

    response = await client.post(
        "/api/inbody/parse",
        files={"file": ("sheet.pdf", pdf, "application/pdf")},
    )

    assert response.status_code == 200, response.text
    assert response.json()["weight_kg"] == 84.7
    assert response.json()["pbf_percent"] == 19.4
    assert response.json()["measured_on"] == "2026-11-07"
    assert response.json()["measured_time"] == "09:15:00"
    assert response.json()["missing"] == []
    rows = await db_session.scalar(select(func.count()).select_from(InbodyScan))
    assert rows == 0
    assert (await client.get("/api/inbody")).json() == []


async def test_pdf_parse_rejects_a_file_without_inbody_numbers(client: AsyncClient) -> None:
    await _register(client, "owner@example.com")

    foreign = await client.post(
        "/api/inbody/parse",
        files={"file": ("note.pdf", _sheet_pdf(["Just a note"]), "application/pdf")},
    )
    assert foreign.status_code == 422

    not_pdf = await client.post(
        "/api/inbody/parse",
        files={"file": ("note.txt", b"hello", "text/plain")},
    )
    assert not_pdf.status_code == 422
    assert not_pdf.json()["detail"] == "Это не PDF"


async def test_invalid_scan_is_rejected(client: AsyncClient) -> None:
    await _register(client, "owner@example.com")
    response = await client.post("/api/inbody", json={**SCAN, "pbf_percent": 0})
    assert response.status_code == 422
    assert (await client.get("/api/inbody")).json() == []


async def test_export_round_trip_and_old_file_without_scans(client: AsyncClient) -> None:
    await _register(client, "owner@example.com")
    assert (await client.post("/api/inbody", json=SCAN)).status_code == 201

    exported = await client.get("/api/export")
    assert exported.status_code == 200, exported.text
    document = exported.json()
    assert document["format_version"] == 1
    assert len(document["inbody_scans"]) == 1
    assert document["inbody_scans"][0]["weight_kg"] == 84.7
    assert "protein_g" not in document

    await client.post("/api/auth/logout")
    await _register(client, "other@example.com")
    imported = await client.post("/api/import", params={"mode": "replace"}, json=document)
    assert imported.status_code == 200, imported.text
    copied = await client.get("/api/inbody")
    assert copied.status_code == 200
    assert copied.json()[0]["weight_kg"] == 84.7
    assert copied.json()[0]["id"] != document["inbody_scans"][0]["id"]

    legacy = {
        **document,
        "inbody_scans": [
            {
                **document["inbody_scans"][0],
                "time_of_day": "evening",
                "fasted": False,
                "after_workout": True,
                "dehydrated": True,
                "creatine_or_salt": True,
            }
        ],
    }
    again = await client.post("/api/import", params={"mode": "replace"}, json=legacy)
    assert again.status_code == 200, again.text
    assert (await client.get("/api/inbody")).json()[0]["weight_kg"] == 84.7

    old_file = dict(document)
    del old_file["inbody_scans"]
    cleared = await client.post("/api/import", params={"mode": "replace"}, json=old_file)
    assert cleared.status_code == 200, cleared.text
    assert (await client.get("/api/inbody")).json() == []
