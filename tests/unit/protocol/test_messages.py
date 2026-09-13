"""Round-trip/versioning tests for the M8 wire protocol (ADR-008)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from rogue.execution.adapter import AdapterDeviceStatus
from rogue.protocol.messages import (
    PROTOCOL_SCHEMA_VERSION,
    AgentAck,
    AgentCommand,
    AgentCommandKind,
    AgentPresence,
    AgentTelemetry,
)


def _status() -> AdapterDeviceStatus:
    return AdapterDeviceStatus(
        device_id="sim-1",
        channel_index=0,
        leased=True,
        configured=True,
        armed=False,
        transmitting=False,
    )


def test_agent_command_round_trips_and_carries_schema_version() -> None:
    command = AgentCommand(
        correlation_id=uuid4(),
        sequence=1,
        kind=AgentCommandKind.ARM,
        device_id="sim-1",
        channel_index=0,
        start_at_seconds=5.0,
    )

    restored = AgentCommand.model_validate(command.model_dump(mode="json"))

    assert restored == command
    assert restored.schema_version == PROTOCOL_SCHEMA_VERSION


def test_agent_command_round_trips_barrier_at() -> None:
    barrier_at = datetime(2026, 1, 1, tzinfo=UTC)
    command = AgentCommand(
        correlation_id=uuid4(),
        sequence=1,
        kind=AgentCommandKind.START,
        device_id="sim-1",
        channel_index=0,
        barrier_at=barrier_at,
    )

    restored = AgentCommand.model_validate(command.model_dump(mode="json"))

    assert restored.barrier_at == barrier_at


def test_agent_command_barrier_at_defaults_to_none() -> None:
    command = AgentCommand(
        correlation_id=uuid4(),
        sequence=1,
        kind=AgentCommandKind.START,
        device_id="sim-1",
        channel_index=0,
    )

    restored = AgentCommand.model_validate(command.model_dump(mode="json"))

    assert restored.barrier_at is None


def test_adapter_device_status_round_trips_actual_tx_start_at_and_last_error() -> None:
    status = AdapterDeviceStatus(
        device_id="sim-1",
        channel_index=0,
        leased=True,
        configured=True,
        armed=True,
        transmitting=True,
        actual_tx_start_at=datetime(2026, 1, 1, tzinfo=UTC),
        last_error="simulated device failure",
    )
    ack = AgentAck(correlation_id=uuid4(), sequence=1, status=status)

    restored = AgentAck.model_validate(ack.model_dump(mode="json"))

    assert restored.status == status


def test_agent_ack_round_trips_with_embedded_status() -> None:
    ack = AgentAck(correlation_id=uuid4(), sequence=1, status=_status())

    restored = AgentAck.model_validate(ack.model_dump(mode="json"))

    assert restored.accepted is True
    assert restored.status == _status()


def test_agent_ack_can_carry_a_structured_error() -> None:
    ack = AgentAck(correlation_id=uuid4(), sequence=2, accepted=False, error="device unreachable")

    restored = AgentAck.model_validate(ack.model_dump(mode="json"))

    assert restored.accepted is False
    assert restored.error == "device unreachable"


def test_agent_presence_round_trips() -> None:
    presence = AgentPresence(agent_id="sim-agent-01", mode="simulated")

    restored = AgentPresence.model_validate(presence.model_dump(mode="json"))

    assert restored.agent_id == "sim-agent-01"
    assert restored.capabilities == []


def test_agent_telemetry_round_trips() -> None:
    telemetry = AgentTelemetry(
        agent_id="sim-agent-01", device_id="sim-1", channel_index=0, status=_status()
    )

    restored = AgentTelemetry.model_validate(telemetry.model_dump(mode="json"))

    assert restored.status == _status()
