"""`RemoteAgentAdapter`: the same `SDRAdapter` Protocol, dispatched over NATS
to a real, separate Agent process instead of an in-process `MockSDRAdapter`
(ADR-008). `rogue.execution.orchestrator` needs no changes to use this —
every method still returns/raises exactly what the Protocol promises.

DB access (device_id -> agent_id routing, aggregate discovered capabilities)
is injected as plain async callables rather than imported directly, keeping
this module free of a `rogue.persistence`/session dependency, the same way
`rogue.execution.orchestrator` stays DB-free and lets `rogue.persistence.run`
own the I/O.
"""

from __future__ import annotations

import itertools
from collections.abc import Awaitable, Callable
from datetime import datetime
from uuid import UUID, uuid4

import nats.errors
from nats.aio.client import Client as NATSClient

from rogue.compiler.models import PhysicalTxChannelCapability, RfWindow
from rogue.domain.recording import IQRecording
from rogue.domain.run import DeviceLease
from rogue.execution.adapter import (
    AdapterDeviceStatus,
    AdapterOperationError,
    SimulatedDeviceFailureError,
)
from rogue.protocol.messages import AgentAck, AgentCommand, AgentCommandKind, RecordingCacheEntry
from rogue.protocol.subjects import agent_command_subject

DEFAULT_COMMAND_TIMEOUT_SECONDS = 5.0

AgentLookup = Callable[[str], Awaitable[str | None]]
CapabilitiesLookup = Callable[[], Awaitable[list[PhysicalTxChannelCapability]]]


class AgentUnreachableError(AdapterOperationError):
    """Raised when no agent is registered for a device, or a command times out."""


class RemoteAgentAdapter:
    """Dispatches `SDRAdapter` operations to a device's owning Agent process."""

    def __init__(
        self,
        nc: NATSClient,
        agent_lookup: AgentLookup,
        capabilities_lookup: CapabilitiesLookup,
        *,
        timeout_seconds: float = DEFAULT_COMMAND_TIMEOUT_SECONDS,
    ) -> None:
        self._nc = nc
        self._agent_lookup = agent_lookup
        self._capabilities_lookup = capabilities_lookup
        self._timeout_seconds = timeout_seconds
        self._sequence = itertools.count(1)

    async def _send(
        self,
        kind: AgentCommandKind,
        device_id: str,
        channel_index: int,
        **fields: object,
    ) -> AgentAck:
        agent_id = await self._agent_lookup(device_id)
        if agent_id is None:
            raise AgentUnreachableError(
                device_id, channel_index, f"no agent is currently registered for device {device_id}"
            )

        command = AgentCommand(
            correlation_id=uuid4(),
            sequence=next(self._sequence),
            kind=kind,
            device_id=device_id,
            channel_index=channel_index,
            **fields,
        )
        try:
            reply = await self._nc.request(
                agent_command_subject(agent_id),
                command.model_dump_json().encode(),
                timeout=self._timeout_seconds,
            )
        except (nats.errors.TimeoutError, nats.errors.NoRespondersError) as exc:
            raise AgentUnreachableError(
                device_id, channel_index, f"agent {agent_id} did not respond to {kind.value}: {exc}"
            ) from exc

        ack = AgentAck.model_validate_json(reply.data)
        if not ack.accepted:
            raise SimulatedDeviceFailureError(device_id, channel_index, kind.value)
        return ack

    async def discover(self) -> list[PhysicalTxChannelCapability]:
        return await self._capabilities_lookup()

    async def reserve(
        self, device_id: str, channel_index: int, run_id: UUID, ttl_seconds: float
    ) -> DeviceLease:
        ack = await self._send(
            AgentCommandKind.RESERVE,
            device_id,
            channel_index,
            run_id=run_id,
            lease_ttl_seconds=ttl_seconds,
        )
        assert ack.lease is not None
        return ack.lease

    async def renew(self, lease: DeviceLease, ttl_seconds: float) -> DeviceLease:
        ack = await self._send(
            AgentCommandKind.RENEW_LEASE,
            lease.device_id,
            lease.channel_index,
            lease=lease,
            lease_ttl_seconds=ttl_seconds,
        )
        assert ack.lease is not None
        return ack.lease

    async def release(self, lease: DeviceLease) -> None:
        await self._send(
            AgentCommandKind.RELEASE, lease.device_id, lease.channel_index, lease=lease
        )

    async def preflight(
        self, device_id: str, channel_index: int, window: RfWindow, recordings: list[IQRecording]
    ) -> None:
        entries = [RecordingCacheEntry.from_recording(r) for r in recordings]
        await self._send(
            AgentCommandKind.PREFLIGHT, device_id, channel_index, window=window, recordings=entries
        )

    async def configure(self, device_id: str, channel_index: int, window: RfWindow) -> None:
        await self._send(AgentCommandKind.CONFIGURE, device_id, channel_index, window=window)

    async def arm(self, device_id: str, channel_index: int, start_at_seconds: float) -> None:
        await self._send(
            AgentCommandKind.ARM, device_id, channel_index, start_at_seconds=start_at_seconds
        )

    async def start(
        self, device_id: str, channel_index: int, barrier_at: datetime | None = None
    ) -> None:
        await self._send(AgentCommandKind.START, device_id, channel_index, barrier_at=barrier_at)

    async def stop(self, device_id: str, channel_index: int) -> None:
        await self._send(AgentCommandKind.STOP, device_id, channel_index)

    async def emergency_stop(self, device_id: str, channel_index: int) -> None:
        await self._send(AgentCommandKind.EMERGENCY_STOP, device_id, channel_index)

    async def status(self, device_id: str, channel_index: int) -> AdapterDeviceStatus:
        ack = await self._send(AgentCommandKind.STATUS, device_id, channel_index)
        assert ack.status is not None
        return ack.status
