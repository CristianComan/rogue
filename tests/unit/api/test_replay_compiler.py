"""End-to-end API tests for the Replay Plan compiler router (M6)."""

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
METADATA_KEY = "recordings/replay-api-test.sigmf-meta"
DATA_KEY = "recordings/replay-api-test.sigmf-data"
DATA_BYTES = b"\x00" * 800


def _metadata_bytes(sample_rate: float = 2_000_000.0) -> bytes:
    document = {
        "global": {"core:datatype": "cf32_le", "core:sample_rate": sample_rate},
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
        "name": "replay-api-test-scenario",
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


def _publish_version_with_recording(client: TestClient) -> tuple[dict, dict]:
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
    draft = _create_draft(client, scenario["id"], missions=[mission])

    published = client.post(f"/scenarios/{scenario['id']}/drafts/{draft['id']}/publish")
    assert published.status_code == 201, published.text
    return scenario, published.json()


def test_compile_returns_a_replay_plan(client: TestClient) -> None:
    scenario, version = _publish_version_with_recording(client)

    response = client.post(
        f"/scenarios/{scenario['id']}/versions/{version['version_number']}/compile",
        json={"duration_s": 20.0},
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["scenario_id"] == scenario["id"]
    assert body["scenario_version_number"] == version["version_number"]
    assert len(body["rf_windows"]) == 1
    assert body["safety_policy_outcome"]["tx_authorized"] is False
    assert all(f["severity"] != "blocking" for f in body["findings"])


def test_compile_is_idempotent_for_the_same_key(client: TestClient) -> None:
    scenario, version = _publish_version_with_recording(client)

    headers = {"Idempotency-Key": "replay-compile-test-key"}
    body = {"duration_s": 20.0}
    endpoint = f"/scenarios/{scenario['id']}/versions/{version['version_number']}/compile"

    first = client.post(endpoint, json=body, headers=headers)
    second = client.post(endpoint, json=body, headers=headers)

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] == second.json()["id"]


def test_compile_missing_version_is_404(client: TestClient) -> None:
    scenario = _create_scenario(client)

    response = client.post(
        f"/scenarios/{scenario['id']}/versions/99/compile", json={"duration_s": 10.0}
    )

    assert response.status_code == 404


def test_compile_infeasible_bandwidth_is_422(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Wider than every configured channel (DEFAULT_CAPABILITY_PROFILE's widest
    # is the X440's 400 MHz) — forces rf_window_infeasible, not just M5's own
    # bandwidth_exceeds_band (which would already fire on a narrower excess).
    monkeypatch.setattr(
        object_store, "get_object_bytes", lambda key: _metadata_bytes(1_000_000_000.0)
    )
    scenario, version = _publish_version_with_recording(client)

    response = client.post(
        f"/scenarios/{scenario['id']}/versions/{version['version_number']}/compile",
        json={"duration_s": 10.0},
    )

    assert response.status_code == 422, response.text
    body = response.json()
    assert any(f["code"] == "rf_window_infeasible" for f in body["findings"])


def test_list_and_get_replay_plans(client: TestClient) -> None:
    scenario, version = _publish_version_with_recording(client)

    compiled = client.post(
        f"/scenarios/{scenario['id']}/versions/{version['version_number']}/compile",
        json={"duration_s": 20.0},
    ).json()

    listed = client.get(f"/scenarios/{scenario['id']}/replay-plans")
    assert listed.status_code == 200
    assert [p["id"] for p in listed.json()] == [compiled["id"]]

    fetched = client.get(f"/scenarios/{scenario['id']}/replay-plans/{compiled['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["id"] == compiled["id"]


def test_get_missing_replay_plan_is_404(client: TestClient) -> None:
    scenario = _create_scenario(client)

    response = client.get(
        f"/scenarios/{scenario['id']}/replay-plans/00000000-0000-4000-8000-000000000000"
    )

    assert response.status_code == 404
