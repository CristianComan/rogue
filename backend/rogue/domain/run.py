"""ScenarioRun: the execution record for a compiled ReplayPlan (M7).

Per docs/architecture/domain-model.md's diagram, a ScenarioRun is an
immutable ReplayPlan reference plus DeviceLease[]/RunEvent[]/evidence that
*do* change over time as the run progresses through prepare/arm/start/stop —
unlike ReplayPlan/ScenarioVersion, this is not a FrozenRogueModel. "Run
evidence is append-only" (domain-model.md section 5) is enforced by
convention in rogue.execution.orchestrator/rogue.persistence.run (only ever
appending to `events`, only ever advancing `status`), not by a type-level
constraint here.

DeviceLease.expires_at (M8) is enforced twice: centrally by
rogue.execution.lease_sweep (renews active runs' leases on a short
interval, emergency-stops a run whose lease lapsed without renewal) and
locally by the Agent process itself, independent of control-plane
reachability (sdr-architecture.md §7) — see
docs/decisions/ADR-008-distributed-agent-protocol.md.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import Field

from rogue.domain.common import IdentifiedMixin, TimestampedMixin
from rogue.domain.validation import ValidationSeverity


class RunStatus(StrEnum):
    """A ScenarioRun's lifecycle state."""

    CREATED = "created"
    PREPARING = "preparing"
    PREPARED = "prepared"
    ARMED = "armed"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    FAILED = "failed"
    EMERGENCY_STOPPED = "emergency_stopped"


class DeviceLease(IdentifiedMixin):
    """One physical channel reserved for the duration of a run."""

    device_id: str
    channel_index: int
    run_id: UUID
    leased_at: datetime
    expires_at: datetime


class RunEventKind(StrEnum):
    """The kind of thing a RunEvent records."""

    RESERVED = "reserved"
    PREFETCH_VERIFIED = "prefetch_verified"
    CONFIGURED = "configured"
    ARMED = "armed"
    STARTED = "started"
    STOPPED = "stopped"
    EMERGENCY_STOPPED = "emergency_stopped"
    LEASE_RENEWED = "lease_renewed"
    ERROR = "error"


class RunEvent(IdentifiedMixin):
    """One immutable, timestamped entry in a run's append-only evidence log."""

    at: datetime
    sequence: int = Field(ge=0)
    kind: RunEventKind
    device_id: str | None = None
    channel_index: int | None = None
    message: str
    severity: ValidationSeverity = ValidationSeverity.WARNING


class ScenarioRun(IdentifiedMixin, TimestampedMixin):
    """The execution record for one attempt to play out a compiled ReplayPlan."""

    scenario_id: UUID
    replay_plan_id: UUID
    operator: str
    status: RunStatus = RunStatus.CREATED
    device_leases: list[DeviceLease] = Field(default_factory=list)
    events: list[RunEvent] = Field(default_factory=list)
