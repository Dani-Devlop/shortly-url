"""POST /api/links/bulk-action — archive / restore / delete up to 100 codes."""

from tests.conftest import AUTH_HEADERS, SECOND_API_KEY
from tests.helpers import shorten


async def _mk(client, n, prefix="blk"):
    codes = []
    for i in range(n):
        link = await shorten(
            client, url=f"https://bulk-action.example/{prefix}/{i}",
            custom_code=f"{prefix}{i}",
        )
        codes.append(link["code"])
    return codes


async def test_bulk_archive_and_restore(client):
    codes = await _mk(client, 3)
    response = await client.post(
        "/api/links/bulk-action",
        json={"action": "archive", "codes": codes},
        headers=AUTH_HEADERS,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["action"] == "archive"
    assert body["updated"] == 3 and body["not_found"] == 0
    assert all(r["status"] == "ok" for r in body["results"])

    listed = (
        await client.get("/api/links?status=archived", headers=AUTH_HEADERS)
    ).json()
    assert {i["code"] for i in listed["items"]} == set(codes)

    restore = await client.post(
        "/api/links/bulk-action",
        json={"action": "restore", "codes": codes},
        headers=AUTH_HEADERS,
    )
    assert restore.status_code == 200
    assert restore.json()["updated"] == 3
    active = (await client.get("/api/links", headers=AUTH_HEADERS)).json()
    assert {i["code"] for i in active["items"]} == set(codes)


async def test_bulk_delete_removes_links(client):
    codes = await _mk(client, 2, prefix="del")
    response = await client.post(
        "/api/links/bulk-action",
        json={"action": "delete", "codes": codes},
        headers=AUTH_HEADERS,
    )
    assert response.status_code == 200
    assert response.json()["updated"] == 2
    listed = (await client.get("/api/links?status=all", headers=AUTH_HEADERS)).json()
    assert listed["total"] == 0
    for code in codes:
        assert (await client.get(f"/{code}", follow_redirects=False)).status_code == 404


async def test_bulk_reports_not_found_per_code(client):
    codes = await _mk(client, 2, prefix="nfx")
    await shorten(
        client, url="https://bulk-action.example/foreign", custom_code="frgn1",
        headers={"X-API-Key": SECOND_API_KEY},
    )
    response = await client.post(
        "/api/links/bulk-action",
        json={"action": "archive", "codes": codes + ["ghost1", "frgn1"]},
        headers=AUTH_HEADERS,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["updated"] == 2 and body["not_found"] == 2
    statuses = {r["code"]: r["status"] for r in body["results"]}
    assert statuses["ghost1"] == "not_found"
    assert statuses["frgn1"] == "not_found"
    assert statuses[codes[0]] == "ok"


async def test_bulk_action_validation_matrix(client):
    codes = await _mk(client, 1, prefix="val")
    cases = [
        {"action": "explode", "codes": codes},          # bad action
        {"action": "archive", "codes": []},             # empty list
        {"action": "archive", "codes": [codes[0]] * 101},  # > 100 codes
        {"action": "archive", "codes": ["bad code!"]},  # invalid charset
        {"codes": codes},                               # missing action
        {"action": "archive"},                          # missing codes
    ]
    for payload in cases:
        response = await client.post(
            "/api/links/bulk-action", json=payload, headers=AUTH_HEADERS
        )
        assert response.status_code == 422, payload
    assert (await client.post("/api/links/bulk-action", json=cases[0])).status_code == 401


async def test_bulk_archive_then_redirect_410(client):
    codes = await _mk(client, 2, prefix="gone")
    await client.post(
        "/api/links/bulk-action",
        json={"action": "archive", "codes": codes},
        headers=AUTH_HEADERS,
    )
    for code in codes:
        response = await client.get(f"/{code}", follow_redirects=False)
        assert response.status_code == 410
        assert response.json()["error"]["code"] == "link_archived"
