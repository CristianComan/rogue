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
from uuid import UUID

from rogue.domain.common import GeoPoint, RogueModel
from rogue.domain.geometry import point_in_polygon
from rogue.domain.receiver import ReceiverType
from rogue.domain.timeline import MissionRelativeTimelineEvent

if TYPE_CHECKING:
    from rogue.domain.receiver import Receiver
    from rogue.domain.rf import RfEmission
    from rogue.domain.scenario import ScenarioVersion

# ZoneType lives in rogue.domain.scenario, which imports this module for
# ValidationFinding — importing ZoneType here at module level would be
# circular. Zone.zone_type is a StrEnum, so comparing against its string
# value works identically without the import.
_TRIGGER_ZONE_TYPE = "trigger"
_NO_FLY_ZONE_TYPE = "no_fly"


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


def _coherent_group_findings(version: ScenarioVersion) -> list[ValidationFinding]:
    """A DroneRfLink.array_group_id must resolve to >=2 receivers.

    This is the reference-integrity half of coherent-group support (ADR-012)
    — the geometry/allocation half lives in rogue.compiler.coherent_groups
    and rogue.compiler.allocation, which assume this check already passed.
    No separate MONITOR-type check is needed here: Receiver's own
    model_validator (rogue.domain.receiver) already guarantees any receiver
    carrying a non-None array_group_id is TDOA or AOA_DOA, never MONITOR.
    """
    findings: list[ValidationFinding] = []
    receivers_by_group: dict[UUID, list[Receiver]] = {}
    for receiver in version.receivers:
        if receiver.array_group_id is not None:
            receivers_by_group.setdefault(receiver.array_group_id, []).append(receiver)

    for mission_index, mission in enumerate(version.missions):
        for link_index, link in enumerate(mission.rf_links):
            if link.array_group_id is None:
                continue
            path = f"missions[{mission_index}].rf_links[{link_index}].array_group_id"
            members = receivers_by_group.get(link.array_group_id, [])
            if len(members) < 2:
                findings.append(
                    ValidationFinding(
                        severity=ValidationSeverity.BLOCKING,
                        code="coherent_group_unresolvable",
                        message=(
                            f"array_group_id {link.array_group_id} must resolve to at least 2 "
                            f"TDOA/AOA_DOA receivers in this ScenarioVersion's receivers, found "
                            f"{len(members)}"
                        ),
                        path=path,
                    )
                )

    return findings


def _zone_reference_findings(version: ScenarioVersion) -> list[ValidationFinding]:
    """Region simulation semantics (ADR-015): ``RfEmission.zone_trigger.zone_id``
    must resolve to a ``TRIGGER``-typed ``Zone``, and
    ``DroneRfLink.observed_by_receiver_id`` must resolve to a ``MONITOR``-typed
    ``Receiver`` — the reference-integrity half, mirroring
    ``_coherent_group_findings``'s precedent for ``array_group_id``. The
    geometry/compiler half (deriving active spans / gated intervals from
    ``rogue.domain.mission_evaluator.zone_crossings`` and applying them in
    ``rogue.compiler.windows``/``rogue.spectrum.occupancy``) is unbuilt
    follow-up work — this reference-integrity check just ensures a future
    compiler pass would have a resolvable zone/receiver to work from.
    """
    findings: list[ValidationFinding] = []
    zones_by_id = {zone.id: zone for zone in version.zones}
    receivers_by_id = {receiver.id: receiver for receiver in version.receivers}

    for mission_index, mission in enumerate(version.missions):
        for link_index, link in enumerate(mission.rf_links):
            link_path = f"missions[{mission_index}].rf_links[{link_index}]"

            if link.observed_by_receiver_id is not None:
                receiver = receivers_by_id.get(link.observed_by_receiver_id)
                if receiver is None or receiver.receiver_type != ReceiverType.MONITOR:
                    findings.append(
                        ValidationFinding(
                            severity=ValidationSeverity.BLOCKING,
                            code="observed_by_receiver_unresolvable",
                            message=(
                                f"observed_by_receiver_id {link.observed_by_receiver_id} must "
                                "resolve to a MONITOR receiver in this ScenarioVersion's receivers"
                            ),
                            path=f"{link_path}.observed_by_receiver_id",
                        )
                    )

            for emission_index, emission in enumerate(link.emissions):
                if emission.zone_trigger is None:
                    continue
                emission_path = f"{link_path}.emissions[{emission_index}].zone_trigger"
                zone = zones_by_id.get(emission.zone_trigger.zone_id)
                if zone is None or zone.zone_type != _TRIGGER_ZONE_TYPE:
                    findings.append(
                        ValidationFinding(
                            severity=ValidationSeverity.BLOCKING,
                            code="zone_trigger_reference_unresolvable",
                            message=(
                                f"zone_trigger.zone_id {emission.zone_trigger.zone_id} must "
                                "resolve to a TRIGGER-typed Zone in this ScenarioVersion's zones"
                            ),
                            path=emission_path,
                        )
                    )

    return findings


_NO_FLY_SAMPLE_FRACTIONS = (0.0, 0.25, 0.5, 0.75, 1.0)


def _no_fly_containment_findings(version: ScenarioVersion) -> list[ValidationFinding]:
    """Region simulation semantics (ADR-015): a mission's trajectory must
    never enter a ``NO_FLY`` zone — BLOCKING, checked at plan-time
    (publish), not runtime. Samples each waypoint-to-waypoint leg at a
    handful of fractions (endpoints + quarters) rather than
    ``mission_evaluator.zone_crossings``'s full sampling cadence — this only
    needs a yes/no containment answer over the mission's whole authored
    span, not interval boundaries, so a coarser, bounded sample per leg is
    enough (a documented approximation, not exact-geometry segment/polygon
    intersection).
    """
    findings: list[ValidationFinding] = []
    no_fly_zones = [z for z in version.zones if z.zone_type == _NO_FLY_ZONE_TYPE]
    if not no_fly_zones:
        return findings

    for mission_index, mission in enumerate(version.missions):
        waypoints = sorted(mission.trajectory.waypoints, key=lambda w: w.sequence_index)
        for from_wp, to_wp in zip(waypoints, waypoints[1:], strict=False):
            for fraction in _NO_FLY_SAMPLE_FRACTIONS:
                lon = from_wp.position.longitude + (
                    to_wp.position.longitude - from_wp.position.longitude
                ) * fraction
                lat = from_wp.position.latitude + (
                    to_wp.position.latitude - from_wp.position.latitude
                ) * fraction
                sample_point = GeoPoint(coordinates=(lon, lat))
                for zone in no_fly_zones:
                    if point_in_polygon(sample_point, zone.polygon):
                        findings.append(
                            ValidationFinding(
                                severity=ValidationSeverity.BLOCKING,
                                code="no_fly_trajectory_containment",
                                message=(
                                    f"mission {mission.id}'s trajectory between waypoints "
                                    f"{from_wp.sequence_index} and {to_wp.sequence_index} enters "
                                    f"no-fly zone {zone.id} ({zone.label or zone.id})"
                                ),
                                path=f"missions[{mission_index}].trajectory",
                            )
                        )
                        break

    return findings


def validate_scenario_version(version: ScenarioVersion) -> list[ValidationFinding]:
    """Run cross-entity consistency checks over a ScenarioVersion.

    Structural invariants already enforced by pydantic validators on the
    individual models are not repeated here.
    """
    findings: list[ValidationFinding] = list(_coherent_group_findings(version))
    findings.extend(_zone_reference_findings(version))
    findings.extend(_no_fly_containment_findings(version))

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
