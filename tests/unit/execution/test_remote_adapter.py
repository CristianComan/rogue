"""Tests for RemoteAgentAdapter (M8, ADR-008) against a fake NATS transport —
deliberately not a real broker, matching CLAUDE.md §10's "default to
simulation" for automated tests. A `@pytest.mark.nats`-marked test elsewhere
covers the real wire round trip against a live broker.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import nats.errors
import pytest

from rogue.domain.run import DeviceLease
from rogue.execution.adapter import AdapterDeviceStatus, SimulatedDeviceFailureError
from rogue.execution.remote_adapter import AgentUnreachableError, RemoteAgentAdapter
from rogue.protocol.messages import AgentAck, AgentCommand

DEVICE = "sim-1"
CHANNEL = 0
AGENT_ID = "sim-agent-01"


@dataclass
class _FakeMsg:
    data: bytes


class _FakeNATS:
    def __init__(self, respond: Any) -> None:
        self._respond = respond
        self.requests: list[tuple[str, bytes]] = []

    async def request(self, subject: str, payload: bytes, timeout: float) -> _FakeMsg:
        self.requests.append((subject, payload))
        return self._respond(subject, AgentCommand.model_validate_json(payload))


class _TimeoutNATS:
    async def request(self, subject: str, payload: bytes, timeout: float) -> _FakeMsg:
        raise nats.errors.TimeoutError


async def _lookup(device_id: str) -> str | None:
    return AGENT_ID if device_id == DEVICE else None


async def _no_agent(device_id: str) -> str | None:
    return None


async def _capabilities() -> list[Any]:
    return []


def _lease() -> DeviceLease:
    now = datetime.now(UTC)
    return DeviceLease(
        device_id=DEVICE,
        channel_index=CHANNEL,
        run_id=uuid4(),
        leased_at=now,
        expires_at=now + timedelta(seconds=30),
    )


async def test_reserve_returns_the_acked_lease() -> None:
    lease = _lease()

    def respond(subject: str, command: AgentCommand) -> _FakeMsg:
        ack = AgentAck(
            correlation_id=command.correlation_id, sequence=command.sequence, lease=lease
        )
        return _FakeMsg(ack.model_dump_json().encode())

    nc = _FakeNATS(respond)
    adapter = RemoteAgentAdapter(nc, _lookup, _capabilities)  # type: ignore[arg-type]

    result = await adapter.reserve(DEVICE, CHANNEL, lease.run_id, ttl_seconds=30.0)

    assert result == lease
    assert nc.requests[0][0] == f"rogue.agents.{AGENT_ID}.cmd"


async def test_status_returns_the_acked_status() -> None:
    status = AdapterDeviceStatus(
        device_id=DEVICE,
        channel_index=CHANNEL,
        leased=True,
        configured=True,
        armed=True,
        transmitting=True,
    )

    def respond(subject: str, command: AgentCommand) -> _FakeMsg:
        ack = AgentAck(
            correlation_id=command.correlation_id, sequence=command.sequence, status=status
        )
        return _FakeMsg(ack.model_dump_json().encode())

    nc = _FakeNATS(respond)
    adapter = RemoteAgentAdapter(nc, _lookup, _capabilities)  # type: ignore[arg-type]

    result = await adapter.status(DEVICE, CHANNEL)

    assert result == status


async def test_rejected_ack_raises_simulated_device_failure() -> None:
    def respond(subject: str, command: AgentCommand) -> _FakeMsg:
        ack = AgentAck(
            correlation_id=command.correlation_id,
            sequence=command.sequence,
            accepted=False,
            error="boom",
        )
        return _FakeMsg(ack.model_dump_json().encode())

    nc = _FakeNATS(respond)
    adapter = RemoteAgentAdapter(nc, _lookup, _capabilities)  # type: ignore[arg-type]

    with pytest.raises(SimulatedDeviceFailureError):
        await adapter.start(DEVICE, CHANNEL)


async def test_unregistered_device_raises_agent_unreachable() -> None:
    nc = _FakeNATS(lambda *_: None)
    adapter = RemoteAgentAdapter(nc, _no_agent, _capabilities)  # type: ignore[arg-type]

    with pytest.raises(AgentUnreachableError):
        await adapter.start(DEVICE, CHANNEL)


async def test_timeout_raises_agent_unreachable() -> None:
    adapter = RemoteAgentAdapter(_TimeoutNATS(), _lookup, _capabilities)  # type: ignore[arg-type]

    with pytest.raises(AgentUnreachableError):
        await adapter.start(DEVICE, CHANNEL)
