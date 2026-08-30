"""End-to-end API tests for the SigMF catalogue router.

The object-storage fetch inside ``rogue.catalogue.ingest`` is monkeypatched
here rather than backed by real MinIO — consistent with
``tests/unit/persistence/test_catalogue.py`` and CLAUDE.md's
simulation-by-default testing rule.
"""

from __future__ import annotations

import hashlib
import json

import pytest
from fastapi.testclient import TestClient

from rogue.storage import object_store
from rogue.storage.object_store import ObjectDigest

METADATA_KEY = "recordings/api-test.sigmf-meta"
DATA_KEY = "recordings/api-test.sigmf-data"
DATA_BYTES = b"\x00" * 800


def _metadata_bytes() -> bytes:
    document = {
        "global": {"core:datatype": "cf32_le", "core:sample_rate": 1_000_000.0},
        "captures": [{"core:frequency": 2_450_000_000.0}],
    }
    return json.dumps(document).encode()


@pytest.fixture(autouse=True)
def _valid_object_store(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(object_store, "get_object_bytes", lambda key: _metadata_bytes())
    monkeypatch.setattr(
        object_store,
        "digest_object",
        lambda key: ObjectDigest(
            sha256=hashlib.sha256(DATA_BYTES).hexdigest(),
            sha512=hashlib.sha512(DATA_BYTES).hexdigest(),
            size_bytes=len(DATA_BYTES),
        ),
    )


def _ingest(client: TestClient, **overrides: object) -> dict:
    body = {
        "metadata_object_key": METADATA_KEY,
        "data_object_key": DATA_KEY,
        "provenance": "api-test",
    }
    body.update(overrides)
    response = client.post("/recordings", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def test_ingest_recording_returns_recording_and_empty_findings(client: TestClient) -> None:
    result = _ingest(client)

    assert result["findings"] == []
    assert result["recording"]["version"] == 1
    assert result["recording"]["sample_count"] == 100


def test_ingest_and_get_recording(client: TestClient) -> None:
    ingested = _ingest(client)["recording"]

    fetched = client.get(f"/recordings/{ingested['id']}")

    assert fetched.status_code == 200
    assert fetched.json()["id"] == ingested["id"]


def test_get_missing_recording_is_404(client: TestClient) -> None:
    response = client.get("/recordings/00000000-0000-4000-8000-000000000000")
    assert response.status_code == 404


def test_ingest_new_version_of_existing_recording(client: TestClient) -> None:
    first = _ingest(client)["recording"]

    second = _ingest(client, recording_id=first["id"])["recording"]

    assert second["id"] == first["id"]
    assert second["version"] == 2

    versions = client.get(f"/recordings/{first['id']}/versions").json()
    assert [v["version"] for v in versions] == [1, 2]


def test_ingest_new_version_of_unknown_recording_is_404(client: TestClient) -> None:
    response = client.post(
        "/recordings",
        json={
            "recording_id": "00000000-0000-4000-8000-000000000000",
            "metadata_object_key": METADATA_KEY,
            "data_object_key": DATA_KEY,
        },
    )
    assert response.status_code == 404


def test_ingest_rejects_invalid_metadata_with_findings(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(object_store, "get_object_bytes", lambda key: b"not json")

    response = client.post(
        "/recordings",
        json={"metadata_object_key": METADATA_KEY, "data_object_key": DATA_KEY},
    )

    assert response.status_code == 422
    assert any(f["code"] == "sigmf_metadata_invalid" for f in response.json()["findings"])


def test_ingest_idempotency_key_replays_response(client: TestClient) -> None:
    headers = {"Idempotency-Key": "ingest-1"}
    body = {
        "metadata_object_key": METADATA_KEY,
        "data_object_key": DATA_KEY,
        "provenance": "idempotent-test",
    }

    first = client.post("/recordings", json=body, headers=headers)
    second = client.post("/recordings", json=body, headers=headers)

    assert first.status_code == second.status_code == 201
    assert first.json()["recording"]["id"] == second.json()["recording"]["id"]
    versions = client.get(f"/recordings/{first.json()['recording']['id']}/versions").json()
    assert len(versions) == 1


def test_list_recordings_filters_by_access_classification(client: TestClient) -> None:
    _ingest(client, access_classification="public", provenance="public-set")
    _ingest(client, access_classification="controlled", provenance="controlled-set")

    response = client.get("/recordings", params={"access_classification": "public"})

    assert response.status_code == 200
    assert {r["provenance"] for r in response.json()} == {"public-set"}


def test_get_missing_version_is_404(client: TestClient) -> None:
    ingested = _ingest(client)["recording"]

    response = client.get(f"/recordings/{ingested['id']}/versions/99")

    assert response.status_code == 404
