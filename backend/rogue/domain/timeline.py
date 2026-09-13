"""Scenario timeline events.

Per docs/architecture/domain-model.md section 4, events may be absolute
scenario time, mission-relative, manual-gated, approved external, or safety
events. The MVP mission engine (M3) only evaluates absolute and
mission-relative events; the other kinds are modelled here as data so the
schema is stable, but no execution semantics are implemented in this
feature.
"""

from __future__ import annotations

from datetime import timedelta
from enum import StrEnum
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field

from rogue.domain.common import IdentifiedMixin


class MissionRelativeAnchor(StrEnum):
    """Point in a mission's lifecycle that a mission-relative event anchors to."""

    MISSION_START = "mission_start"
    WAYPOINT = "waypoint"
    AREA_ENTRY = "area_entry"
    PHASE_COMPLETION = "phase_completion"


class SafetyEventKind(StrEnum):
    """Recognized safety-triggered timeline events."""

    LEASE_EXPIRY = "lease_expiry"
    ALARM = "alarm"
    CLOCK_DEGRADATION = "clock_degradation"
    UNDERRUN = "underrun"
    NO_TRANSMIT_VIOLATION = "no_transmit_violation"
    EMERGENCY_STOP = "emergency_stop"


class TimelineEventBase(IdentifiedMixin):
    """Fields shared by every timeline event kind."""

    label: str | None = None
    notes: str | None = None


class AbsoluteTimelineEvent(TimelineEventBase):
    """Fires at a fixed offset from scenario start (T+hh:mm:ss.sss)."""

    kind: Literal["absolute"] = "absolute"
    scenario_time_offset: timedelta


class MissionRelativeTimelineEvent(TimelineEventBase):
    """Fires relative to a named mission's lifecycle."""

    kind: Literal["mission_relative"] = "mission_relative"
    mission_id: UUID
    anchor: MissionRelativeAnchor
    waypoint_sequence_index: int | None = None
    offset: timedelta = timedelta(0)


class ManualGatedTimelineEvent(TimelineEventBase):
    """Requires an explicit operator acknowledgement to fire."""

    kind: Literal["manual_gated"] = "manual_gated"
    gate_description: str


class ExternalTimelineEvent(TimelineEventBase):
    """Fires on an approved external system signal."""

    kind: Literal["external"] = "external"
    source: str
    trigger_reference: str


class SafetyTimelineEvent(TimelineEventBase):
    """A safety-triggered event; never author-scheduled."""

    kind: Literal["safety"] = "safety"
    safety_kind: SafetyEventKind

    scenario_time_offset: timedelta | None = None


TimelineEvent = Annotated[
    AbsoluteTimelineEvent
    | MissionRelativeTimelineEvent
    | ManualGatedTimelineEvent
    | ExternalTimelineEvent
    | SafetyTimelineEvent,
    Field(discriminator="kind"),
]
