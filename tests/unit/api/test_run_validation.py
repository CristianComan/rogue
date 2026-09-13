"""End-to-end API tests for the independent RF validation endpoint (M14)."""

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
METADATA_KEY = "recordings/run-validate-api-test.sigmf-meta"
DATA_KEY = "recordings/run-validate-api-test.sigmf-data"
DATA_BYTES = b"\x00" * 800

MONITOR_RECEIVER = {
    "name": "rx-1",
    "receiver_type": "monitor",
    "position": {"type": "Point", "coordinates": [13.42, 52.50]},
}


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
        "name": "run-validate-api-test-scenario",
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


def _compile_a_plan(client: TestClient) -> tuple[dict, dict]:
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
        client, scenario["id"], missions=[mission], receivers=[MONITOR_RECEIVER]
    )
    published = client.post(f"/scenarios/{scenario['id']}/drafts/{draft['id']}/publish")
    assert published.status_code == 201, published.text
    version = published.json()

    compiled = client.post(
        f"/scenarios/{scenario['id']}/versions/{version['version_number']}/compile",
        json={"duration_s": 20.0},
    )
    assert compiled.status_code == 201, compiled.text
    return scenario, compiled.json()


def _runs_url(scenario_id: str, plan_id: str, suffix: str = "") -> str:
    return f"/scenarios/{scenario_id}/replay-plans/{plan_id}/runs{suffix}"


def _running_run(client: TestClient) -> tuple[dict, dict, str]:
    scenario, plan = _compile_a_plan(client)
    run = client.post(
        _runs_url(scenario["id"], plan["id"]), json={"operator": "test-operator"}
    ).json()
    run_id = run["id"]
    armed = client.post(_runs_url(scenario["id"], plan["id"], f"/{run_id}/arm"))
    assert armed.status_code == 200, armed.text
    started = client.post(_runs_url(scenario["id"], plan["id"], f"/{run_id}/start"))
    assert started.status_code == 200, started.text
    assert started.json()["status"] == "running"
    return scenario, plan, run_id


def test_validate_run_appends_a_validation_report(client: TestClient) -> None:
    scenario, plan, run_id = _running_run(client)
    window = plan["rf_windows"][0]
    at_seconds = (window["start_seconds"] + window["end_seconds"]) / 2

    response = client.post(
        _runs_url(scenario["id"], plan["id"], f"/{run_id}/validate"),
        json={"at_seconds": at_seconds},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body["validation_reports"]) == 1
    assert body["validation_reports"][0]["receiver_id"]
    assert any(e["kind"] == "validation_recorded" for e in body["events"])

    fetched = client.get(_runs_url(scenario["id"], plan["id"], f"/{run_id}"))
    assert fetched.status_code == 200
    assert fetched.json() == body


def test_validate_run_is_idempotent_for_the_same_key(client: TestClient) -> None:
    scenario, plan, run_id = _running_run(client)
    window = plan["rf_windows"][0]
    at_seconds = (window["start_seconds"] + window["end_seconds"]) / 2
    headers = {"Idempotency-Key": "run-validate-test-key"}
    body = {"at_seconds": at_seconds}

    first = client.post(
        _runs_url(scenario["id"], plan["id"], f"/{run_id}/validate"), json=body, headers=headers
    )
    second = client.post(
        _runs_url(scenario["id"], plan["id"], f"/{run_id}/validate"), json=body, headers=headers
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert len(first.json()["validation_reports"]) == len(second.json()["validation_reports"]) == 1


def test_validate_unknown_run_returns_404(client: TestClient) -> None:
    scenario, plan = _compile_a_plan(client)

    response = client.post(
        _runs_url(scenario["id"], plan["id"], "/00000000-0000-0000-0000-000000000000/validate"),
        json={"at_seconds": 1.0},
    )

    assert response.status_code == 404


def test_validate_run_still_in_prepared_status_returns_409(client: TestClient) -> None:
    scenario, plan = _compile_a_plan(client)
    run = client.post(
        _runs_url(scenario["id"], plan["id"]), json={"operator": "test-operator"}
    ).json()
    assert run["status"] == "prepared"

    response = client.post(
        _runs_url(scenario["id"], plan["id"], f"/{run['id']}/validate"),
        json={"at_seconds": 1.0},
    )

    assert response.status_code == 409
