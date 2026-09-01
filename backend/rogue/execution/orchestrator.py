"""The prepare/arm/start/stop state machine (M7), pure and DB-free — mirrors
rogue.compiler.compile's split from rogue.persistence.replay: this module
takes already-loaded domain objects and an adapter, and returns a new
ScenarioRun; rogue.persistence.run does the surrounding database I/O.

Each channel is configured/armed/started once, using its *earliest*
allocation's window — runtime re-configuration mid-run on a BAND_SWITCH
event is not simulated in this pass (see ADR-007's assumptions); a full
scheduler loop that walks the compiled timeline live is deferred alongside
the real distributed Agent work (M8).
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from rogue.compiler.models import Allocation, ReplayPlan, RfWindow
from rogue.domain.recording import IQRecording
from rogue.domain.run import RunEvent, RunEventKind, RunStatus, ScenarioRun
from rogue.domain.validation import ValidationSeverity
from rogue.execution.adapter import SDRAdapter, SimulatedDeviceFailureError


class InvalidRunTransitionError(Exception):
    """Raised when a lifecycle call is made from the wrong RunStatus."""

    def __init__(self, expected: RunStatus, actual: RunStatus, action: str) -> None:
        super().__init__(f"cannot {action} a run in status {actual!r}, expected {expected!r}")
        self.expected = expected
        self.actual = actual
        self.action = action


def _first_allocation_per_channel(plan: ReplayPlan) -> dict[tuple[str, int], Allocation]:
    """The earliest allocation for each (device_id, channel_index) — see module docstring."""
    by_channel: dict[tuple[str, int], Allocation] = {}
    for allocation in sorted(plan.allocations, key=lambda a: a.start_seconds):
        key = (allocation.device_id, allocation.channel_index)
        by_channel.setdefault(key, allocation)
    return by_channel


def _window_for(plan: ReplayPlan, allocation: Allocation) -> RfWindow | None:
    for window in plan.rf_windows:
        if (
            window.window_key == allocation.window_key
            and window.start_seconds == allocation.start_seconds
            and window.end_seconds == allocation.end_seconds
        ):
            return window
    return None


class _RunBuilder:
    """Accumulates events/leases for one lifecycle call, appending only."""

    def __init__(self, run: ScenarioRun) -> None:
        self._run = run
        self.events = list(run.events)
        self.leases = list(run.device_leases)
        self._sequence = len(run.events)

    def event(
        self,
        kind: RunEventKind,
        message: str,
        *,
        device_id: str | None = None,
        channel_index: int | None = None,
        severity: ValidationSeverity = ValidationSeverity.WARNING,
    ) -> None:
        self._sequence += 1
        self.events.append(
            RunEvent(
                at=datetime.now(UTC),
                sequence=self._sequence,
                kind=kind,
                device_id=device_id,
                channel_index=channel_index,
                message=message,
                severity=severity,
            )
        )

    def fail(
        self,
        message: str,
        *,
        device_id: str | None = None,
        channel_index: int | None = None,
    ) -> ScenarioRun:
        self.event(
            RunEventKind.ERROR,
            message,
            device_id=device_id,
            channel_index=channel_index,
            severity=ValidationSeverity.BLOCKING,
        )
        return self._run.model_copy(
            update={"status": RunStatus.FAILED, "events": self.events, "device_leases": self.leases}
        )

    def advance(self, status: RunStatus) -> ScenarioRun:
        return self._run.model_copy(
            update={"status": status, "events": self.events, "device_leases": self.leases}
        )


async def prepare_run(
    run: ScenarioRun,
    plan: ReplayPlan,
    recordings: dict[tuple[UUID, int], IQRecording],
    adapter: SDRAdapter,
) -> ScenarioRun:
    """Reserve every allocated channel, verify every referenced recording's
    hashes against the catalogue's current state, then preflight/configure
    each channel. Fails (returns a FAILED run) on the first problem rather
    than partially preparing.
    """
    if run.status != RunStatus.CREATED:
        raise InvalidRunTransitionError(RunStatus.CREATED, run.status, "prepare")

    builder = _RunBuilder(run)
    channels = _first_allocation_per_channel(plan)

    for (device_id, channel_index), _allocation in channels.items():
        try:
            lease = await adapter.reserve(device_id, channel_index, run.id)
        except SimulatedDeviceFailureError as exc:
            return builder.fail(str(exc), device_id=device_id, channel_index=channel_index)
        builder.leases.append(lease)
        builder.event(
            RunEventKind.RESERVED,
            f"reserved {device_id}:{channel_index}",
            device_id=device_id,
            channel_index=channel_index,
        )

    for entry in plan.recording_manifest:
        recording = recordings.get((entry.recording_id, entry.version))
        if recording is None:
            return builder.fail(
                f"recording {entry.recording_id} v{entry.version} is no longer in the catalogue"
            )
        if (
            recording.sha256_metadata != entry.sha256_metadata
            or recording.sha256_data != entry.sha256_data
        ):
            return builder.fail(
                f"recording {entry.recording_id} v{entry.version} no longer matches the "
                "plan's pinned checksums"
            )
        builder.event(
            RunEventKind.PREFETCH_VERIFIED,
            f"verified recording {entry.recording_id} v{entry.version}",
        )

    for (device_id, channel_index), allocation in channels.items():
        window = _window_for(plan, allocation)
        if window is None:
            return builder.fail(
                "allocation references a window that isn't in the plan",
                device_id=device_id,
                channel_index=channel_index,
            )
        try:
            await adapter.preflight(device_id, channel_index, window)
            await adapter.configure(device_id, channel_index, window)
        except SimulatedDeviceFailureError as exc:
            return builder.fail(str(exc), device_id=device_id, channel_index=channel_index)
        builder.event(
            RunEventKind.CONFIGURED,
            f"configured {device_id}:{channel_index}",
            device_id=device_id,
            channel_index=channel_index,
        )

    return builder.advance(RunStatus.PREPARED)


async def arm_run(run: ScenarioRun, plan: ReplayPlan, adapter: SDRAdapter) -> ScenarioRun:
    if run.status != RunStatus.PREPARED:
        raise InvalidRunTransitionError(RunStatus.PREPARED, run.status, "arm")

    builder = _RunBuilder(run)
    for (device_id, channel_index), allocation in _first_allocation_per_channel(plan).items():
        try:
            await adapter.arm(device_id, channel_index, allocation.start_seconds)
        except SimulatedDeviceFailureError as exc:
            return builder.fail(str(exc), device_id=device_id, channel_index=channel_index)
        builder.event(
            RunEventKind.ARMED,
            f"armed {device_id}:{channel_index}",
            device_id=device_id,
            channel_index=channel_index,
        )
    return builder.advance(RunStatus.ARMED)


async def start_run(run: ScenarioRun, plan: ReplayPlan, adapter: SDRAdapter) -> ScenarioRun:
    if run.status != RunStatus.ARMED:
        raise InvalidRunTransitionError(RunStatus.ARMED, run.status, "start")

    builder = _RunBuilder(run)
    for device_id, channel_index in _first_allocation_per_channel(plan):
        try:
            await adapter.start(device_id, channel_index)
        except SimulatedDeviceFailureError as exc:
            return builder.fail(str(exc), device_id=device_id, channel_index=channel_index)
        builder.event(
            RunEventKind.STARTED,
            f"started {device_id}:{channel_index}",
            device_id=device_id,
            channel_index=channel_index,
        )
    return builder.advance(RunStatus.RUNNING)


async def stop_run(run: ScenarioRun, plan: ReplayPlan, adapter: SDRAdapter) -> ScenarioRun:
    if run.status not in (RunStatus.ARMED, RunStatus.RUNNING):
        raise InvalidRunTransitionError(RunStatus.RUNNING, run.status, "stop")

    builder = _RunBuilder(run)
    for device_id, channel_index in _first_allocation_per_channel(plan):
        try:
            await adapter.stop(device_id, channel_index)
        except SimulatedDeviceFailureError as exc:
            return builder.fail(str(exc), device_id=device_id, channel_index=channel_index)
        builder.event(
            RunEventKind.STOPPED,
            f"stopped {device_id}:{channel_index}",
            device_id=device_id,
            channel_index=channel_index,
        )
    return builder.advance(RunStatus.STOPPED)


async def emergency_stop_run(
    run: ScenarioRun, plan: ReplayPlan, adapter: SDRAdapter
) -> ScenarioRun:
    """Always succeeds in reaching EMERGENCY_STOPPED, from any status.

    Per CLAUDE.md's safety rules, this path is dedicated-tested and must
    never itself fail — a per-channel adapter error is recorded as an event
    but does not stop the sweep across the remaining channels, and never
    prevents the run from landing in EMERGENCY_STOPPED.
    """
    builder = _RunBuilder(run)
    for device_id, channel_index in _first_allocation_per_channel(plan):
        try:
            await adapter.emergency_stop(device_id, channel_index)
            builder.event(
                RunEventKind.EMERGENCY_STOPPED,
                f"emergency-stopped {device_id}:{channel_index}",
                device_id=device_id,
                channel_index=channel_index,
                severity=ValidationSeverity.BLOCKING,
            )
        except Exception as exc:  # noqa: BLE001 - emergency stop must not itself fail
            builder.event(
                RunEventKind.ERROR,
                f"emergency-stop reported an error for {device_id}:{channel_index}: {exc}",
                device_id=device_id,
                channel_index=channel_index,
                severity=ValidationSeverity.BLOCKING,
            )
    return builder.advance(RunStatus.EMERGENCY_STOPPED)
