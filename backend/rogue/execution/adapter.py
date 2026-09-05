"""Vendor-neutral SDR adapter contract (sdr-architecture.md section 2) and
its first-class simulated implementation (section 8: "not a throwaway
mock").

Real vendor adapters (EttusX440Adapter, DeepwaveAIR7311Adapter) are M9/M10;
this module only needs to exist and be stable enough for
rogue.execution.orchestrator to depend on it, per CLAUDE.md's sequencing
rule ("do not jump directly to X440/AIR7311 implementation before ... the
simulated adapter boundary is stable").

Methods are scoped to one `(device_id, channel_index)` pair rather than one
adapter instance per channel — this models "one Agent, many devices"
(sdr-architecture.md section 1), matching docker-compose.yml's single
`simulated-agent` service.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID

from rogue.compiler.models import PhysicalTxChannelCapability, RfWindow
from rogue.domain.run import DeviceLease


class SimulatedDeviceFailureError(Exception):
    """Raised by MockSDRAdapter when a test has configured this step to fail."""

    def __init__(self, device_id: str, channel_index: int, method: str) -> None:
        super().__init__(f"simulated device failure: {device_id}:{channel_index}.{method}()")
        self.device_id = device_id
        self.channel_index = channel_index
        self.method = method


@dataclass(frozen=True)
class AdapterDeviceStatus:
    """A channel's current state, as the adapter itself understands it."""

    device_id: str
    channel_index: int
    leased: bool
    configured: bool
    armed: bool
    transmitting: bool


class SDRAdapter(Protocol):
    """The vendor-neutral operations every SDR adapter implementation exposes."""

    async def discover(self) -> list[PhysicalTxChannelCapability]: ...
    async def reserve(self, device_id: str, channel_index: int, run_id: UUID) -> DeviceLease: ...
    async def release(self, lease: DeviceLease) -> None: ...
    async def preflight(self, device_id: str, channel_index: int, window: RfWindow) -> None: ...
    async def configure(self, device_id: str, channel_index: int, window: RfWindow) -> None: ...
    async def arm(self, device_id: str, channel_index: int, start_at_seconds: float) -> None: ...
    async def start(self, device_id: str, channel_index: int) -> None: ...
    async def stop(self, device_id: str, channel_index: int) -> None: ...
    async def emergency_stop(self, device_id: str, channel_index: int) -> None: ...
    async def status(self, device_id: str, channel_index: int) -> AdapterDeviceStatus: ...


_SIMULATED_TRANSFER_DELAY_S = 0.01


@dataclass
class _ChannelState:
    leased: bool = False
    configured: bool = False
    armed: bool = False
    transmitting: bool = False


class MockSDRAdapter:
    """A first-class simulated `SDRAdapter` — models transfer delay and
    injectable device failure (sdr-architecture.md section 8). Clock drift,
    underrun and command-loss simulation are not modelled in this pass; see
    ADR-007's assumptions.

    `fail_on` lets a test force a specific (device_id, channel_index,
    method_name) call to raise `SimulatedDeviceFailureError` — this is what
    makes "emergency-stop after a device failure," not just "emergency-stop
    from the happy path," actually testable.
    """

    def __init__(
        self,
        capabilities: list[PhysicalTxChannelCapability],
        fail_on: set[tuple[str, int, str]] | None = None,
    ) -> None:
        self._capabilities = capabilities
        self._fail_on = fail_on or set()
        self._channels: dict[tuple[str, int], _ChannelState] = {}

    def _state(self, device_id: str, channel_index: int) -> _ChannelState:
        return self._channels.setdefault((device_id, channel_index), _ChannelState())

    async def _simulate(self, device_id: str, channel_index: int, method: str) -> None:
        await asyncio.sleep(_SIMULATED_TRANSFER_DELAY_S)
        if (device_id, channel_index, method) in self._fail_on:
            raise SimulatedDeviceFailureError(device_id, channel_index, method)

    async def discover(self) -> list[PhysicalTxChannelCapability]:
        await asyncio.sleep(_SIMULATED_TRANSFER_DELAY_S)
        return list(self._capabilities)

    async def reserve(self, device_id: str, channel_index: int, run_id: UUID) -> DeviceLease:
        await self._simulate(device_id, channel_index, "reserve")
        self._state(device_id, channel_index).leased = True
        return DeviceLease(
            device_id=device_id,
            channel_index=channel_index,
            run_id=run_id,
            leased_at=datetime.now(UTC),
        )

    async def release(self, lease: DeviceLease) -> None:
        await self._simulate(lease.device_id, lease.channel_index, "release")
        self._state(lease.device_id, lease.channel_index).leased = False

    async def preflight(self, device_id: str, channel_index: int, window: RfWindow) -> None:
        await self._simulate(device_id, channel_index, "preflight")

    async def configure(self, device_id: str, channel_index: int, window: RfWindow) -> None:
        await self._simulate(device_id, channel_index, "configure")
        self._state(device_id, channel_index).configured = True

    async def arm(self, device_id: str, channel_index: int, start_at_seconds: float) -> None:
        await self._simulate(device_id, channel_index, "arm")
        self._state(device_id, channel_index).armed = True

    async def start(self, device_id: str, channel_index: int) -> None:
        await self._simulate(device_id, channel_index, "start")
        self._state(device_id, channel_index).transmitting = True

    async def stop(self, device_id: str, channel_index: int) -> None:
        await self._simulate(device_id, channel_index, "stop")
        state = self._state(device_id, channel_index)
        state.transmitting = False
        state.armed = False

    async def emergency_stop(self, device_id: str, channel_index: int) -> None:
        # Deliberately does not consult _fail_on/raise — emergency stop must
        # always succeed regardless of simulated failure state (CLAUDE.md
        # section 10: emergency stop paths receive dedicated tests, and a
        # stop path that itself can fail defeats the point).
        state = self._state(device_id, channel_index)
        state.transmitting = False
        state.armed = False

    async def status(self, device_id: str, channel_index: int) -> AdapterDeviceStatus:
        state = self._state(device_id, channel_index)
        return AdapterDeviceStatus(
            device_id=device_id,
            channel_index=channel_index,
            leased=state.leased,
            configured=state.configured,
            armed=state.armed,
            transmitting=state.transmitting,
        )
