"""Top-level scenario aggregate: Scenario, ScenarioDraft and ScenarioVersion.

Per docs/architecture/domain-model.md sections 2 and 5: Scenario is the
stable identity; ScenarioDraft is an editable, optimistically-concurrent
working copy; ScenarioVersion is the immutable, schema-versioned published
document. ScenarioRun and the compiled Replay Plan are out of scope for
this feature (later milestones M2/M6+).
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import Field

from rogue.domain.common import (
    FrozenRogueModel,
    GeoPolygon,
    IdentifiedMixin,
    TimestampedMixin,
)
from rogue.domain.mission import DroneMission
from rogue.domain.receiver import Receiver
from rogue.domain.recording import RecordingReference
from rogue.domain.timeline import TimelineEvent
from rogue.domain.validation import ValidationFinding

SCENARIO_SCHEMA_VERSION = "1.0"


class ZoneType(StrEnum):
    """Kind of area annotation attached to a scenario version."""

    OPERATIONAL_AREA = "operational_area"
    NO_TRANSMIT = "no_transmit"
    NO_FLY = "no_fly"
    RESTRICTED = "restricted"
    CUSTOM = "custom"


class Zone(IdentifiedMixin):
    """A named area/restricted-zone polygon."""

    zone_type: ZoneType
    polygon: GeoPolygon
    label: str | None = None
    notes: str | None = None


class Scenario(IdentifiedMixin, TimestampedMixin):
    """Stable scenario identity, independent of any particular version."""

    name: str
    owner: str
    tags: list[str] = Field(default_factory=list)
    coordinate_system: str = "EPSG:4326"
    area_of_operation: GeoPolygon
    variables: dict[str, Any] = Field(default_factory=dict)
    current_version_id: UUID | None = None


class ScenarioDraft(IdentifiedMixin, TimestampedMixin):
    """Editable working copy of a scenario, with optimistic concurrency."""

    scenario_id: UUID
    base_version_id: UUID | None = None
    revision: int = Field(default=0, ge=0)
    author: str

    zones: list[Zone] = Field(default_factory=list)
    missions: list[DroneMission] = Field(default_factory=list)
    receivers: list[Receiver] = Field(default_factory=list)
    timeline_events: list[TimelineEvent] = Field(default_factory=list)
    recordings: list[RecordingReference] = Field(default_factory=list)


class ScenarioVersion(FrozenRogueModel):
    """Immutable, schema-versioned published scenario document."""

    id: UUID
    scenario_id: UUID
    version_number: int = Field(ge=1)
    schema_version: str = SCENARIO_SCHEMA_VERSION

    zones: list[Zone] = Field(default_factory=list)
    missions: list[DroneMission] = Field(default_factory=list)
    receivers: list[Receiver] = Field(default_factory=list)
    timeline_events: list[TimelineEvent] = Field(default_factory=list)
    recordings: list[RecordingReference] = Field(default_factory=list)

    author: str
    change_note: str | None = None
    validation_findings: list[ValidationFinding] = Field(default_factory=list)
