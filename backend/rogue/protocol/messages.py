"""Versioned NATS message shapes exchanged between the control plane and an
SDR Agent process (`sdr-architecture.md` §4: "every command/ACK includes
correlation ID, sequence, timestamps, state and structured errors").

Reuses existing shapes rather than redefining them: `AdapterDeviceStatus`
and `DeviceLease` are the same types `rogue.execution.adapter.SDRAdapter`
already returns in-process, so `RemoteAgentAdapter`
(`rogue.execution.remote_adapter`) can hand an `AgentAck`'s payload
straight to its caller without a second translation layer.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import Field

from rogue.compiler.models import PhysicalTxChannelCapability, RfWindow
from rogue.domain.common import RogueModel, utc_now
from rogue.domain.recording import IQRecording
from rogue.domain.run import DeviceLease
from rogue.execution.adapter import AdapterDeviceStatus

PROTOCOL_SCHEMA_VERSION = "1.0"


class RecordingCacheEntry(RogueModel):
    """What an Agent needs to fetch+verify one SigMF asset into its local
    cache (sdr-architecture.md §6) — a subset of `IQRecording`'s fields,
    carried on a PREFLIGHT command rather than requiring the Agent to have
    its own catalogue-database access.
    """

    recording_id: UUID
    version: int
    metadata_object_key: str
    data_object_key: str
    sha256_metadata: str
    sha256_data: str

    @classmethod
    def from_recording(cls, recording: IQRecording) -> RecordingCacheEntry:
        return cls(
            recording_id=recording.id,
            version=recording.version,
            metadata_object_key=recording.metadata_object_key,
            data_object_key=recording.data_object_key,
            sha256_metadata=recording.sha256_metadata,
            sha256_data=recording.sha256_data,
        )


class AgentCommandKind(StrEnum):
    """One `SDRAdapter` operation, carried over the wire (sdr-architecture.md §4)."""

    RESERVE = "reserve"
    RELEASE = "release"
    PREFLIGHT = "preflight"
    CONFIGURE = "configure"
    ARM = "arm"
    START = "start"
    STOP = "stop"
    EMERGENCY_STOP = "emergency_stop"
    STATUS = "status"
    RENEW_LEASE = "renew_lease"


class AgentCommand(RogueModel):
    """One request sent to an Agent's per-agent command subject."""

    schema_version: str = PROTOCOL_SCHEMA_VERSION
    correlation_id: UUID
    sequence: int
    issued_at: datetime = Field(default_factory=utc_now)
    kind: AgentCommandKind
    device_id: str
    channel_index: int
    run_id: UUID | None = None
    window: RfWindow | None = None
    recordings: list[RecordingCacheEntry] | None = None
    start_at_seconds: float | None = None
    lease_ttl_seconds: float | None = None
    lease: DeviceLease | None = None


class AgentAck(RogueModel):
    """The reply to one `AgentCommand`, echoing its correlation/sequence."""

    schema_version: str = PROTOCOL_SCHEMA_VERSION
    correlation_id: UUID
    sequence: int
    at: datetime = Field(default_factory=utc_now)
    accepted: bool = True
    status: AdapterDeviceStatus | None = None
    lease: DeviceLease | None = None
    error: str | None = None


class AgentPresence(RogueModel):
    """Periodic heartbeat published on the shared presence subject."""

    schema_version: str = PROTOCOL_SCHEMA_VERSION
    agent_id: str
    mode: str
    capabilities: list[PhysicalTxChannelCapability] = Field(default_factory=list)
    seen_at: datetime = Field(default_factory=utc_now)


class AgentTelemetry(RogueModel):
    """Per-channel status snapshot published on an Agent's telemetry subject."""

    schema_version: str = PROTOCOL_SCHEMA_VERSION
    agent_id: str
    device_id: str
    channel_index: int
    status: AdapterDeviceStatus
    at: datetime = Field(default_factory=utc_now)
