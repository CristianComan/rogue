"""End-to-end API tests for the simulated ScenarioRun execution router (M7)."""

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
METADATA_KEY = "recordings/run-api-test.sigmf-meta"
DATA_KEY = "recordings/run-api-test.sigmf-data"
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
    body = {"name": "run-api-test-scenario", "owner": "test-operator", "area_of_operation": AREA}
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
    draft = _create_draft(client, scenario["id"], missions=[mission])
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


def test_create_run_prepares_it(client: TestClient) -> None:
    scenario, plan = _compile_a_plan(client)

    response = client.post(
        _runs_url(scenario["id"], plan["id"]), json={"operator": "test-operator"}
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "prepared"
    assert body["scenario_id"] == scenario["id"]
    assert body["replay_plan_id"] == plan["id"]


def test_create_run_is_idempotent_for_the_same_key(client: TestClient) -> None:
    scenario, plan = _compile_a_plan(client)
    headers = {"Idempotency-Key": "run-create-test-key"}
    body = {"operator": "test-operator"}

    first = client.post(_runs_url(scenario["id"], plan["id"]), json=body, headers=headers)
    second = client.post(_runs_url(scenario["id"], plan["id"]), json=body, headers=headers)

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] == second.json()["id"]


def test_full_lifecycle_via_api(client: TestClient) -> None:
    scenario, plan = _compile_a_plan(client)
    run = client.post(
        _runs_url(scenario["id"], plan["id"]), json={"operator": "test-operator"}
    ).json()
    run_id = run["id"]

    armed = client.post(_runs_url(scenario["id"], plan["id"], f"/{run_id}/arm"))
    assert armed.status_code == 200, armed.text
    assert armed.json()["status"] == "armed"

    started = client.post(_runs_url(scenario["id"], plan["id"], f"/{run_id}/start"))
    assert started.status_code == 200
    assert started.json()["status"] == "running"

    stopped = client.post(_runs_url(scenario["id"], plan["id"], f"/{run_id}/stop"))
    assert stopped.status_code == 200
    assert stopped.json()["status"] == "stopped"

    fetched = client.get(_runs_url(scenario["id"], plan["id"], f"/{run_id}"))
    assert fetched.status_code == 200
    assert len(fetched.json()["events"]) == len(stopped.json()["events"])


def test_arm_is_idempotent_for_the_same_key(client: TestClient) -> None:
    scenario, plan = _compile_a_plan(client)
    run = client.post(
        _runs_url(scenario["id"], plan["id"]), json={"operator": "test-operator"}
    ).json()
    headers = {"Idempotency-Key": "run-arm-test-key"}

    first = client.post(
        _runs_url(scenario["id"], plan["id"], f"/{run['id']}/arm"), headers=headers
    )
    second = client.post(
        _runs_url(scenario["id"], plan["id"], f"/{run['id']}/arm"), headers=headers
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json() == second.json()


def test_arm_before_prepared_is_409(client: TestClient) -> None:
    scenario, plan = _compile_a_plan(client)
    run = client.post(
        _runs_url(scenario["id"], plan["id"]), json={"operator": "test-operator"}
    ).json()
    # Already prepared by creation; arming twice in a row without a fresh
    # run is the simplest way to exercise the wrong-status 409 without
    # reaching into persistence internals.
    client.post(_runs_url(scenario["id"], plan["id"], f"/{run['id']}/arm"))

    second_arm = client.post(_runs_url(scenario["id"], plan["id"], f"/{run['id']}/arm"))

    assert second_arm.status_code == 409


def test_emergency_stop_is_reachable_from_running(client: TestClient) -> None:
    scenario, plan = _compile_a_plan(client)
    run = client.post(
        _runs_url(scenario["id"], plan["id"]), json={"operator": "test-operator"}
    ).json()
    client.post(_runs_url(scenario["id"], plan["id"], f"/{run['id']}/arm"))
    client.post(_runs_url(scenario["id"], plan["id"], f"/{run['id']}/start"))

    response = client.post(_runs_url(scenario["id"], plan["id"], f"/{run['id']}/emergency-stop"))

    assert response.status_code == 200
    assert response.json()["status"] == "emergency_stopped"


def test_create_run_missing_plan_is_404(client: TestClient) -> None:
    scenario = _create_scenario(client)

    response = client.post(
        _runs_url(scenario["id"], "00000000-0000-4000-8000-000000000000"),
        json={"operator": "test-operator"},
    )

    assert response.status_code == 404


def test_list_and_get_runs(client: TestClient) -> None:
    scenario, plan = _compile_a_plan(client)
    created = client.post(
        _runs_url(scenario["id"], plan["id"]), json={"operator": "test-operator"}
    ).json()

    listed = client.get(_runs_url(scenario["id"], plan["id"]))
    assert listed.status_code == 200
    assert [r["id"] for r in listed.json()] == [created["id"]]

    fetched = client.get(_runs_url(scenario["id"], plan["id"], f"/{created['id']}"))
    assert fetched.status_code == 200
    assert fetched.json()["id"] == created["id"]


def test_get_missing_run_is_404(client: TestClient) -> None:
    scenario, plan = _compile_a_plan(client)

    response = client.get(
        _runs_url(scenario["id"], plan["id"], "/00000000-0000-4000-8000-000000000000")
    )

    assert response.status_code == 404
