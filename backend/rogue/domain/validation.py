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
    from rogue.domain.rf import RfEmission
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


def _resolvable_span_seconds(emission: RfEmission) -> tuple[float, float] | None:
    """(start, end) seconds if resolvable purely from the emission's own fields.

    An emission with no explicit ``duration_override`` that plays a
    recording to its natural length isn't resolvable here without a
    catalogue lookup this module doesn't have; a looping emission is
    open-ended by design. Both are skipped rather than guessed at, so
    overlap detection below is conservative/best-effort, not exhaustive.
    """
    if emission.loop or emission.duration_override is None:
        return None
    start = emission.start_offset.total_seconds()
    return start, start + emission.duration_override.total_seconds()


def validate_scenario_version(version: ScenarioVersion) -> list[ValidationFinding]:
    """Run cross-entity consistency checks over a ScenarioVersion.

    Structural invariants already enforced by pydantic validators on the
    individual models are not repeated here.
    """
    findings: list[ValidationFinding] = []

    # No dangling-recording-reference check here: ScenarioVersion.recordings
    # is always derived from these same emissions
    # (domain.scenario.derive_recording_references), never authored
    # separately, so an emission's recording can never be missing from it.
    known_mission_ids = {mission.id for mission in version.missions}

    for mission_index, mission in enumerate(version.missions):
        for link_index, link in enumerate(mission.rf_links):
            resolved_spans: list[tuple[int, float, float]] = []
            for emission_index, emission in enumerate(link.emissions):
                span = _resolvable_span_seconds(emission)
                if span is not None:
                    resolved_spans.append((emission_index, span[0], span[1]))

            resolved_spans.sort(key=lambda s: s[1])
            for (prev_index, _prev_start, prev_end), (next_index, next_start, _next_end) in zip(
                resolved_spans, resolved_spans[1:], strict=False
            ):
                if next_start < prev_end:
                    findings.append(
                        ValidationFinding(
                            severity=ValidationSeverity.BLOCKING,
                            code="overlapping_emissions",
                            message=(
                                f"RfEmissions {prev_index} and {next_index} on this RfLink "
                                "overlap in time"
                            ),
                            path=(
                                f"missions[{mission_index}].rf_links[{link_index}]"
                                f".emissions[{next_index}]"
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
