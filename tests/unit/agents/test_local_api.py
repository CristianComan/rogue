"""Tests for the local HTTP command ingress (ADR-019, M19a): a request must
produce exactly the same ACK `agent.py`'s NATS path already produces for the
same `AgentCommand`, since `local_api.py` is a transport adapter over
`AgentRuntime.handle_command`, not a second set of command semantics.
"""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from agents.common.agent import AgentRuntime
from agents.common.local_api import create_local_api
from fastapi.testclient import TestClient

from rogue.execution.adapter import MockSDRAdapter
from rogue.protocol.messages import AgentCommand, AgentCommandKind

DEVICE = "sim-1"
CHANNEL = 0


def _client(tmp_path: Path) -> TestClient:
    runtime = AgentRuntime(agent_id="sim-agent-local", capabilities=[], cache_dir=tmp_path)
    return TestClient(create_local_api(runtime))


def _command_payload(kind: AgentCommandKind, **overrides: object) -> dict[str, object]:
    command = AgentCommand(
        correlation_id=uuid4(),
        sequence=1,
        kind=kind,
        device_id=DEVICE,
        channel_index=CHANNEL,
        **overrides,
    )
    return command.model_dump(mode="json")


def test_health_reports_agent_id_and_mode(tmp_path: Path) -> None:
    client = _client(tmp_path)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"agent_id": "sim-agent-local", "mode": "simulated"}


def test_submit_command_reserve_returns_an_accepted_ack_with_a_lease(tmp_path: Path) -> None:
    client = _client(tmp_path)
    payload = _command_payload(
        AgentCommandKind.RESERVE, run_id=str(uuid4()), lease_ttl_seconds=30.0
    )

    response = client.post("/commands", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["accepted"] is True
    assert body["correlation_id"] == payload["correlation_id"]
    assert body["lease"]["device_id"] == DEVICE


def test_submit_command_on_adapter_failure_returns_a_rejected_ack(tmp_path: Path) -> None:
    runtime = AgentRuntime(agent_id="sim-agent-local", capabilities=[], cache_dir=tmp_path)
    runtime.adapter = MockSDRAdapter(capabilities=[], fail_on={(DEVICE, CHANNEL, "start")})
    client = TestClient(create_local_api(runtime))
    payload = _command_payload(AgentCommandKind.START)

    response = client.post("/commands", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["accepted"] is False
    assert body["error"] is not None


def test_submit_command_rejects_a_malformed_body(tmp_path: Path) -> None:
    client = _client(tmp_path)

    response = client.post("/commands", json={"kind": "reserve"})

    assert response.status_code == 422
