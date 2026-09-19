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
(sdr-architecture.md section 1). In `MockSDRAdapter`'s case that's one
process-wide instance per API process (M7, `rogue.persistence.run`); the
M8 `AgentRuntime` (`agents/common/agent.py`) constructs one of these per
real Agent process instead, one per docker-compose `simulated-agent-*`
service.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol
from uuid import UUID

from rogue.compiler.models import PhysicalTxChannelCapability, RfWindow
from rogue.domain.recording import IQRecording
from rogue.domain.run import DeviceLease


class AdapterOperationError(Exception):
    """Base for any `SDRAdapter` call that failed for a given channel.

    `rogue.execution.orchestrator` catches this base (not the specific
    subclasses) so a remote Agent's `AgentUnreachableError`
    (`rogue.execution.remote_adapter`, M8) fails a run the same way an
    in-process `SimulatedDeviceFailureError` always has — no new
    orchestrator branches needed to add a second `SDRAdapter`
    implementation (ADR-008).
    """

    def __init__(self, device_id: str, channel_index: int, message: str) -> None:
        super().__init__(message)
        self.device_id = device_id
        self.channel_index = channel_index


class SimulatedDeviceFailureError(AdapterOperationError):
    """Raised by MockSDRAdapter when a test has configured this step to fail."""

    def __init__(self, device_id: str, channel_index: int, method: str) -> None:
        super().__init__(
            device_id,
            channel_index,
            f"simulated device failure: {device_id}:{channel_index}.{method}()",
        )
        self.method = method


@dataclass(frozen=True)
class AdapterDeviceStatus:
    """A channel's current state, as the adapter itself understands it.

    ``actual_tx_start_at`` (M11) is only meaningful once ``transmitting`` is
    true — it is the wall-clock instant this channel actually began
    transmitting, as opposed to when a ``start()`` call was merely accepted.
    For a barrier-synchronized start (see ``start()`` below) these two can
    differ by design; comparing ``actual_tx_start_at`` across every channel
    in one barrier group is how synchronization is *measured*, not just
    declared (``sdr-architecture.md`` §5, M11's exit criterion).

    ``last_error`` surfaces a failure that happened in the background after
    a barrier-scheduled ``start()`` already returned (it must return
    immediately — see ``start()``'s docstring — so a failure can't simply be
    raised back to the original caller). ``rogue.execution.orchestrator``
    polls this after a barrier group's target time to distinguish a real
    failure from a channel that merely hasn't reported back yet.
    """

    device_id: str
    channel_index: int
    leased: bool
    configured: bool
    armed: bool
    transmitting: bool
    actual_tx_start_at: datetime | None = None
    last_error: str | None = None


class SDRAdapter(Protocol):
    """The vendor-neutral operations every SDR adapter implementation exposes."""

    async def discover(self) -> list[PhysicalTxChannelCapability]: ...
    async def reserve(
        self, device_id: str, channel_index: int, run_id: UUID, ttl_seconds: float
    ) -> DeviceLease: ...
    async def renew(self, lease: DeviceLease, ttl_seconds: float) -> DeviceLease: ...
    async def release(self, lease: DeviceLease) -> None: ...
    async def preflight(
        self, device_id: str, channel_index: int, window: RfWindow, recordings: list[IQRecording]
    ) -> None: ...
    async def configure(self, device_id: str, channel_index: int, window: RfWindow) -> None: ...
    async def arm(self, device_id: str, channel_index: int, start_at_seconds: float) -> None: ...
    async def start(
        self, device_id: str, channel_index: int, barrier_at: datetime | None = None
    ) -> None: ...
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
    actual_tx_start_at: datetime | None = None
    last_error: str | None = None
    barrier_task: asyncio.Task[None] | None = None


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

    async def reserve(
        self, device_id: str, channel_index: int, run_id: UUID, ttl_seconds: float
    ) -> DeviceLease:
        await self._simulate(device_id, channel_index, "reserve")
        self._state(device_id, channel_index).leased = True
        leased_at = datetime.now(UTC)
        return DeviceLease(
            device_id=device_id,
            channel_index=channel_index,
            run_id=run_id,
            leased_at=leased_at,
            expires_at=leased_at + timedelta(seconds=ttl_seconds),
        )

    async def renew(self, lease: DeviceLease, ttl_seconds: float) -> DeviceLease:
        # Deliberately not gated by _fail_on/_simulate's delay: renewal is the
        # lease-sweep's periodic heartbeat, not a one-off configuration step a
        # test would want to inject failure into (see module docstring).
        return lease.model_copy(
            update={"expires_at": datetime.now(UTC) + timedelta(seconds=ttl_seconds)}
        )

    async def release(self, lease: DeviceLease) -> None:
        await self._simulate(lease.device_id, lease.channel_index, "release")
        self._state(lease.device_id, lease.channel_index).leased = False

    async def preflight(
        self, device_id: str, channel_index: int, window: RfWindow, recordings: list[IQRecording]
    ) -> None:
        # In-process mode has no separate Agent process to cache into — the
        # real local-cache download only happens in agents/common/cache.py,
        # reached via RemoteAgentAdapter's PREFLIGHT command (ADR-008).
        await self._simulate(device_id, channel_index, "preflight")

    async def configure(self, device_id: str, channel_index: int, window: RfWindow) -> None:
        await self._simulate(device_id, channel_index, "configure")
        self._state(device_id, channel_index).configured = True

    async def arm(self, device_id: str, channel_index: int, start_at_seconds: float) -> None:
        await self._simulate(device_id, channel_index, "arm")
        self._state(device_id, channel_index).armed = True

    async def start(
        self, device_id: str, channel_index: int, barrier_at: datetime | None = None
    ) -> None:
        if barrier_at is None:
            await self._simulate(device_id, channel_index, "start")
            state = self._state(device_id, channel_index)
            state.transmitting = True
            state.actual_tx_start_at = datetime.now(UTC)
            return
        # Barrier-synchronized start (M11): the actual keying is scheduled
        # as a background task and this call returns as soon as it's
        # scheduled, not once it fires. This is not an optimization — it's
        # required for correctness. A real Agent's command loop
        # (agents/common/agent.py) processes one NATS message at a time; if
        # this awaited the sleep itself, a second channel owned by the same
        # Agent would only begin *its own* wait after the first one's
        # already elapsed, breaking the barrier for every multi-channel
        # Agent (see ADR-013).
        state = self._state(device_id, channel_index)
        state.last_error = None
        state.barrier_task = asyncio.create_task(
            self._start_at_barrier(device_id, channel_index, barrier_at)
        )

    async def _start_at_barrier(
        self, device_id: str, channel_index: int, barrier_at: datetime
    ) -> None:
        delay = (barrier_at - datetime.now(UTC)).total_seconds()
        if delay > 0:
            await asyncio.sleep(delay)
        state = self._state(device_id, channel_index)
        try:
            await self._simulate(device_id, channel_index, "start")
        except SimulatedDeviceFailureError as exc:
            state.last_error = str(exc)
            return
        state.transmitting = True
        state.actual_tx_start_at = datetime.now(UTC)

    async def stop(self, device_id: str, channel_index: int) -> None:
        await self._simulate(device_id, channel_index, "stop")
        state = self._state(device_id, channel_index)
        state.transmitting = False
        state.armed = False
        state.actual_tx_start_at = None

    async def emergency_stop(self, device_id: str, channel_index: int) -> None:
        # Deliberately does not consult _fail_on/raise — emergency stop must
        # always succeed regardless of simulated failure state (CLAUDE.md
        # section 10: emergency stop paths receive dedicated tests, and a
        # stop path that itself can fail defeats the point).
        state = self._state(device_id, channel_index)
        if state.barrier_task is not None:
            state.barrier_task.cancel()
            state.barrier_task = None
        state.transmitting = False
        state.armed = False
        state.actual_tx_start_at = None

    async def status(self, device_id: str, channel_index: int) -> AdapterDeviceStatus:
        state = self._state(device_id, channel_index)
        return AdapterDeviceStatus(
            device_id=device_id,
            channel_index=channel_index,
            leased=state.leased,
            configured=state.configured,
            armed=state.armed,
            transmitting=state.transmitting,
            actual_tx_start_at=state.actual_tx_start_at,
            last_error=state.last_error,
        )
