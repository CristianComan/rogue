"""ROGUE scenario domain model.

Typed, versioned, hardware-independent scenario entities: Scenario,
ScenarioDraft, ScenarioVersion, timeline events, drone missions/
trajectories, RF links/emissions/frequency behaviour, recording references
and receivers. See docs/architecture/domain-model.md for the canonical
description and CLAUDE.md section 3 for the architecture invariants this
package must uphold (hardware independence, Replay Plan boundary,
immutability of published versions).

SDR control, scenario persistence/API and the RF Environment Compiler are
later milestones and are intentionally not implemented here.
"""

from __future__ import annotations

from rogue.domain.common import GeoLineString, GeoPoint, GeoPolygon
from rogue.domain.mission import (
    AltitudeReference,
    DroneMission,
    MissionStartPolicy,
    MissionTemplate,
    Platform,
    PlatformCategory,
    Trajectory,
    Waypoint,
)
from rogue.domain.receiver import Receiver, ReceiverType
from rogue.domain.recording import AccessClassification, IQRecording, RecordingReference
from rogue.domain.rf import (
    DroneRfLink,
    FrequencyBehaviour,
    FrequencyEvent,
    FrequencySwitchingMode,
    FrequencyTransitionType,
    ResourcePreference,
    RfBand,
    RfEmission,
    RfLinkRole,
    TimingSyncClass,
)
from rogue.domain.scenario import (
    SCENARIO_SCHEMA_VERSION,
    Scenario,
    ScenarioDraft,
    ScenarioVersion,
    Zone,
    ZoneType,
)
from rogue.domain.timeline import (
    AbsoluteTimelineEvent,
    ExternalTimelineEvent,
    ManualGatedTimelineEvent,
    MissionRelativeAnchor,
    MissionRelativeTimelineEvent,
    SafetyEventKind,
    SafetyTimelineEvent,
    TimelineEvent,
)
from rogue.domain.validation import ValidationFinding, ValidationSeverity, validate_scenario_version

__all__ = [
    "SCENARIO_SCHEMA_VERSION",
    "AbsoluteTimelineEvent",
    "AccessClassification",
    "AltitudeReference",
    "DroneMission",
    "DroneRfLink",
    "ExternalTimelineEvent",
    "FrequencyBehaviour",
    "FrequencyEvent",
    "FrequencySwitchingMode",
    "FrequencyTransitionType",
    "GeoLineString",
    "GeoPoint",
    "GeoPolygon",
    "IQRecording",
    "ManualGatedTimelineEvent",
    "MissionRelativeAnchor",
    "MissionRelativeTimelineEvent",
    "MissionStartPolicy",
    "MissionTemplate",
    "Platform",
    "PlatformCategory",
    "Receiver",
    "ReceiverType",
    "RecordingReference",
    "ResourcePreference",
    "RfBand",
    "RfEmission",
    "RfLinkRole",
    "SafetyEventKind",
    "SafetyTimelineEvent",
    "Scenario",
    "ScenarioDraft",
    "ScenarioVersion",
    "TimelineEvent",
    "TimingSyncClass",
    "Trajectory",
    "ValidationFinding",
    "ValidationSeverity",
    "Waypoint",
    "Zone",
    "ZoneType",
    "validate_scenario_version",
]
