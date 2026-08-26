"""End-to-end API tests for the scenario draft/version/clone/validation router."""

from __future__ import annotations

from fastapi.testclient import TestClient

AREA = {
    "type": "Polygon",
    "coordinates": [[[13.0, 52.0], [13.5, 52.0], [13.5, 52.5], [13.0, 52.5], [13.0, 52.0]]],
}


def _create_scenario(client: TestClient, **overrides: object) -> dict:
    body = {"name": "api-test-scenario", "owner": "test-operator", "area_of_operation": AREA}
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


def test_create_and_get_scenario(client: TestClient) -> None:
    created = _create_scenario(client)

    fetched = client.get(f"/scenarios/{created['id']}")

    assert fetched.status_code == 200
    assert fetched.json()["name"] == "api-test-scenario"


def test_get_missing_scenario_is_404(client: TestClient) -> None:
    response = client.get("/scenarios/00000000-0000-4000-8000-000000000000")
    assert response.status_code == 404


def test_list_scenarios_filters_by_owner(client: TestClient) -> None:
    _create_scenario(client, owner="alice", name="alice-scenario")
    _create_scenario(client, owner="bob", name="bob-scenario")

    response = client.get("/scenarios", params={"owner": "alice"})

    assert response.status_code == 200
    assert {s["owner"] for s in response.json()} == {"alice"}


def test_create_scenario_idempotency_key_replays_response(client: TestClient) -> None:
    body = {"name": "idempotent-scenario", "owner": "test-operator", "area_of_operation": AREA}
    headers = {"Idempotency-Key": "create-scenario-1"}

    first = client.post("/scenarios", json=body, headers=headers)
    second = client.post("/scenarios", json=body, headers=headers)

    assert first.status_code == second.status_code == 201
    assert first.json()["id"] == second.json()["id"]


def test_create_scenario_idempotency_key_reuse_with_different_body_conflicts(
    client: TestClient,
) -> None:
    headers = {"Idempotency-Key": "create-scenario-conflict"}
    client.post(
        "/scenarios",
        json={"name": "one", "owner": "test-operator", "area_of_operation": AREA},
        headers=headers,
    )

    response = client.post(
        "/scenarios",
        json={"name": "two", "owner": "test-operator", "area_of_operation": AREA},
        headers=headers,
    )

    assert response.status_code == 409


def test_create_draft_and_fetch(client: TestClient) -> None:
    scenario = _create_scenario(client)

    draft = _create_draft(client, scenario["id"])
    fetched = client.get(f"/scenarios/{scenario['id']}/drafts/{draft['id']}")

    assert fetched.status_code == 200
    assert fetched.json()["revision"] == 0


def test_create_draft_on_missing_scenario_is_404(client: TestClient) -> None:
    response = client.post(
        "/scenarios/00000000-0000-4000-8000-000000000000/drafts",
        json={"author": "test-operator"},
    )
    assert response.status_code == 404


def test_update_draft_conflict_on_stale_revision(client: TestClient) -> None:
    scenario = _create_scenario(client)
    draft = _create_draft(client, scenario["id"])

    response = client.put(
        f"/scenarios/{scenario['id']}/drafts/{draft['id']}",
        json={"author": "test-operator", "expected_revision": 5},
    )

    assert response.status_code == 409


def test_update_draft_success_bumps_revision(client: TestClient) -> None:
    scenario = _create_scenario(client)
    draft = _create_draft(client, scenario["id"])

    response = client.put(
        f"/scenarios/{scenario['id']}/drafts/{draft['id']}",
        json={"author": "new-author", "expected_revision": 0},
    )

    assert response.status_code == 200
    assert response.json()["revision"] == 1
    assert response.json()["author"] == "new-author"


def test_validate_empty_draft_returns_warning_not_blocking(client: TestClient) -> None:
    scenario = _create_scenario(client)
    draft = _create_draft(client, scenario["id"])

    response = client.post(f"/scenarios/{scenario['id']}/drafts/{draft['id']}/validate")

    assert response.status_code == 200
    findings = response.json()
    assert any(f["code"] == "empty_scenario" for f in findings)
    assert all(f["severity"] != "blocking" for f in findings)


def test_publish_empty_draft_succeeds_and_creates_version(client: TestClient) -> None:
    scenario = _create_scenario(client)
    draft = _create_draft(client, scenario["id"])

    response = client.post(f"/scenarios/{scenario['id']}/drafts/{draft['id']}/publish")

    assert response.status_code == 201
    assert response.json()["version_number"] == 1

    scenario_after = client.get(f"/scenarios/{scenario['id']}").json()
    assert scenario_after["current_version_id"] == response.json()["id"]


def test_publish_idempotency_key_replays_same_version(client: TestClient) -> None:
    scenario = _create_scenario(client)
    draft = _create_draft(client, scenario["id"])
    headers = {"Idempotency-Key": "publish-1"}

    first = client.post(
        f"/scenarios/{scenario['id']}/drafts/{draft['id']}/publish", headers=headers
    )
    second = client.post(
        f"/scenarios/{scenario['id']}/drafts/{draft['id']}/publish", headers=headers
    )

    assert first.status_code == second.status_code == 201
    assert first.json()["id"] == second.json()["id"]
    # Replayed, not re-published: still only one version exists.
    versions = client.get(f"/scenarios/{scenario['id']}/versions").json()
    assert len(versions) == 1


def test_publish_rejects_dangling_reference_with_findings(client: TestClient) -> None:
    scenario = _create_scenario(client)
    mission = {
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
                "emissions": [
                    {
                        "recording": {
                            "recording_id": "00000000-0000-4000-8000-000000000001",
                            "version": 1,
                        }
                    }
                ],
            }
        ],
    }
    draft = _create_draft(client, scenario["id"], missions=[mission], recordings=[])

    response = client.post(f"/scenarios/{scenario['id']}/drafts/{draft['id']}/publish")

    assert response.status_code == 422
    assert any(f["code"] == "dangling_recording_reference" for f in response.json()["findings"])
    assert client.get(f"/scenarios/{scenario['id']}/versions").json() == []


def test_get_and_list_versions(client: TestClient) -> None:
    scenario = _create_scenario(client)
    draft = _create_draft(client, scenario["id"])
    published = client.post(f"/scenarios/{scenario['id']}/drafts/{draft['id']}/publish").json()

    fetched = client.get(f"/scenarios/{scenario['id']}/versions/{published['version_number']}")
    listed = client.get(f"/scenarios/{scenario['id']}/versions")

    assert fetched.status_code == 200
    assert fetched.json()["id"] == published["id"]
    assert [v["version_number"] for v in listed.json()] == [1]


def test_get_missing_version_is_404(client: TestClient) -> None:
    scenario = _create_scenario(client)
    response = client.get(f"/scenarios/{scenario['id']}/versions/99")
    assert response.status_code == 404


def test_clone_scenario_creates_new_scenario_and_draft(client: TestClient) -> None:
    scenario = _create_scenario(client)
    draft = _create_draft(client, scenario["id"])
    client.post(f"/scenarios/{scenario['id']}/drafts/{draft['id']}/publish")

    response = client.post(
        f"/scenarios/{scenario['id']}/clone",
        json={"name": "cloned-scenario", "owner": "clone-owner"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["scenario_id"] != scenario["id"]
    cloned = client.get(f"/scenarios/{body['scenario_id']}").json()
    assert cloned["name"] == "cloned-scenario"
