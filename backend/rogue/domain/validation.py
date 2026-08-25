"""Cross-entity scenario validation.

Structural invariants (ranges, closed polygons, non-empty lists, ...) are
enforced by field/model validators on the individual entities. This module
covers the reference-integrity and consistency checks that span multiple
entities within a ScenarioVersion, per docs/architecture/domain-model.md
section 6: schema/references, geometry, mission timing/kinematics,
recording integrity and timeline consistency. RF allocation and hardware
compatibility are compiler/readiness concerns (M5/M6) and are out of scope
here, per CLAUDE.md rule 3.
"""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING

from rogue.domain.common import RogueModel
from rogue.domain.timeline import MissionRelativeTimelineEvent

if TYPE_CHECKING:
    from rogue.domain.scenario import ScenarioVersion


class ValidationSeverity(StrEnum):
    """Distinguishes advisory findings from findings that block publish/run."""

    WARNING = "warning"
    BLOCKING = "blocking"


class ValidationFinding(RogueModel):
    """A single validation result, scoped to a JSON-pointer-like path."""

    severity: ValidationSeverity
    code: str
    message: str
    path: str


def validate_scenario_version(version: ScenarioVersion) -> list[ValidationFinding]:
    """Run cross-entity consistency checks over a ScenarioVersion.

    Structural invariants already enforced by pydantic validators on the
    individual models are not repeated here.
    """
    findings: list[ValidationFinding] = []

    known_recording_ids = {ref.recording_id for ref in version.recordings}
    known_mission_ids = {mission.id for mission in version.missions}

    for mission_index, mission in enumerate(version.missions):
        for link_index, link in enumerate(mission.rf_links):
            for emission_index, emission in enumerate(link.emissions):
                if emission.recording.recording_id not in known_recording_ids:
                    findings.append(
                        ValidationFinding(
                            severity=ValidationSeverity.BLOCKING,
                            code="dangling_recording_reference",
                            message=(
                                f"RfEmission references recording "
                                f"{emission.recording.recording_id} which is not listed in "
                                "ScenarioVersion.recordings"
                            ),
                            path=(
                                f"missions[{mission_index}].rf_links[{link_index}]"
                                f".emissions[{emission_index}].recording.recording_id"
                            ),
                        )
                    )

    for event_index, event in enumerate(version.timeline_events):
        if isinstance(event, MissionRelativeTimelineEvent):
            if event.mission_id not in known_mission_ids:
                findings.append(
                    ValidationFinding(
                        severity=ValidationSeverity.BLOCKING,
                        code="dangling_mission_reference",
                        message=(
                            f"TimelineEvent references mission {event.mission_id} which is not "
                            "present in ScenarioVersion.missions"
                        ),
                        path=f"timeline_events[{event_index}].mission_id",
                    )
                )
            elif event.waypoint_sequence_index is not None:
                mission = next(m for m in version.missions if m.id == event.mission_id)
                indices = {w.sequence_index for w in mission.trajectory.waypoints}
                if event.waypoint_sequence_index not in indices:
                    findings.append(
                        ValidationFinding(
                            severity=ValidationSeverity.BLOCKING,
                            code="dangling_waypoint_reference",
                            message=(
                                f"TimelineEvent references waypoint "
                                f"{event.waypoint_sequence_index} which does not exist on "
                                f"mission {event.mission_id}"
                            ),
                            path=f"timeline_events[{event_index}].waypoint_sequence_index",
                        )
                    )

    if not version.missions and not version.receivers:
        findings.append(
            ValidationFinding(
                severity=ValidationSeverity.WARNING,
                code="empty_scenario",
                message="ScenarioVersion defines neither missions nor receivers",
                path="$",
            )
        )

    return findings
