"""End-to-end API tests for the RF spectrum planner router (M5)."""

from __future__ import annotations

import hashlib
import json

import pytest
from fastapi.testclient import TestClient

from rogue.storage import object_store
from rogue.storage.object_store import ObjectDigest

AREA = {
    "type": "Polygon",
    "coordinates": [[[13.0, 52.0], [13.5, 52.0], [13.5, 52.5], [13.0, 52.5], [13.0, 52.0]]],
}
METADATA_KEY = "recordings/spectrum-api-test.sigmf-meta"
DATA_KEY = "recordings/spectrum-api-test.sigmf-data"
DATA_BYTES = b"\x00" * 800


def _metadata_bytes() -> bytes:
    document = {
        "global": {"core:datatype": "cf32_le", "core:sample_rate": 2_000_000.0},
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


def _create_scenario(client: TestClient, **overrides: object) -> dict:
    body = {
        "name": "spectrum-api-test-scenario",
        "owner": "test-operator",
        "area_of_operation": AREA,
    }
    body.update(overrides)
    response = client.post("/scenarios", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def _create_draft(client: TestClient, scenario_id: str, **overrides: object) -> dict:
    body = {"author": "test-operator"}
    body.update(overrides)
    response = client.post(f"/scenarios/{scenario_id}/drafts", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def _mission_with_recording(recording_id: str) -> dict:
    return {
        "name": "recon-1",
        "platform": {"name": "Quad", "category": "multirotor", "max_speed_mps": 18.0},
        "trajectory": {
            "template": "waypoint_transit",
            "default_speed_mps": 12.0,
            "waypoints": [
                {
                    "sequence_index": 0,
                    "position": {"type": "Point", "coordinates": [13.4, 52.2]},
                    "altitude_m": 100.0,
                },
                {
                    "sequence_index": 1,
                    "position": {"type": "Point", "coordinates": [13.45, 52.25]},
                    "altitude_m": 100.0,
                },
            ],
        },
        "rf_links": [
            {
                "role": "c2",
                "band": {"freq_min_hz": 2.4e9, "freq_max_hz": 2.4835e9},
                "frequency_behaviour": {
                    "mode": "scripted",
                    "scripted_changes": [{"at_offset": "PT0S", "frequency_hz": 2.412e9}],
                },
                "emissions": [{"recording": {"recording_id": recording_id, "version": 1}}],
            }
        ],
    }


def test_spectrum_state_returns_occupied_band(client: TestClient) -> None:
    ingested = client.post(
        "/recordings",
        json={
            "metadata_object_key": METADATA_KEY,
            "data_object_key": DATA_KEY,
            "provenance": "api-test",
        },
    ).json()["recording"]

    scenario = _create_scenario(client)
    mission = _mission_with_recording(ingested["id"])
    draft = _create_draft(
        client,
        scenario["id"],
        missions=[mission],
        recordings=[{"recording_id": ingested["id"], "version": 1}],
    )

    response = client.post(
        f"/scenarios/{scenario['id']}/drafts/{draft['id']}/spectrum", json={"at_seconds": 0.0}
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body["occupied_bands"]) == 1
    assert body["occupied_bands"][0]["center_frequency_hz"] == 2.412e9
    assert body["findings"] == []


def test_spectrum_state_for_missing_draft_is_404(client: TestClient) -> None:
    scenario = _create_scenario(client)

    response = client.post(
        f"/scenarios/{scenario['id']}/drafts/00000000-0000-4000-8000-000000000000/spectrum",
        json={"at_seconds": 0.0},
    )

    assert response.status_code == 404
