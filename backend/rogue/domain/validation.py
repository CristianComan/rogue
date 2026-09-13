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
from itertools import combinations
from typing import TYPE_CHECKING
from uuid import UUID

from rogue.domain.common import GeoPoint, RogueModel
from rogue.domain.geometry import point_in_polygon, polygons_intersect
from rogue.domain.mission import MissionTemplate
from rogue.domain.mission_evaluator import orbit_period_seconds, zone_crossings
from rogue.domain.receiver import ReceiverType
from rogue.domain.timeline import MissionRelativeTimelineEvent

if TYPE_CHECKING:
    from rogue.domain.mission import DroneMission
    from rogue.domain.receiver import Receiver
    from rogue.domain.rf import RfEmission
    from rogue.domain.scenario import ScenarioVersion, Zone

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


def _antimeridian_aware_lerp(a: GeoPoint, b: GeoPoint, fraction: float) -> GeoPoint:
    """Straight-line interpolation between two points, taking the shorter
    path across the +/-180 deg antimeridian rather than naively sweeping
    through longitude 0 for a short hop across the date line.
    """
    lon_delta = b.longitude - a.longitude
    if lon_delta > 180.0:
        lon_delta -= 360.0
    elif lon_delta < -180.0:
        lon_delta += 360.0
    lon = a.longitude + lon_delta * fraction
    if lon > 180.0:
        lon -= 360.0
    elif lon < -180.0:
        lon += 360.0
    lat = a.latitude + (b.latitude - a.latitude) * fraction
    return GeoPoint(coordinates=(lon, lat))


def _no_fly_finding(
    mission: DroneMission, mission_index: int, zone: Zone, detail: str
) -> ValidationFinding:
    return ValidationFinding(
        severity=ValidationSeverity.BLOCKING,
        code="no_fly_trajectory_containment",
        message=(
            f"mission {mission.id}'s {detail} enters no-fly zone {zone.id} "
            f"({zone.label or zone.id})"
        ),
        path=f"missions[{mission_index}].trajectory",
    )


def _orbit_no_fly_findings(
    mission: DroneMission, mission_index: int, no_fly_zones: list[Zone]
) -> list[ValidationFinding]:
    """ORBIT's authored waypoints are a center/radius reference, not path
    points — the actual flown path is the circle between them, which
    straight-leg chord sampling (the fallback below) would check against
    the wrong geometry entirely. Samples the real path via
    ``zone_crossings``/``evaluate_mission_position`` over one full lap
    instead (an ORBIT repeats identically forever, so one period is enough
    to observe the whole geometric path).
    """
    try:
        period = orbit_period_seconds(mission.trajectory)
        crossings_by_zone = {
            zone.id: zone_crossings(mission, zone.polygon, 0.0, period) for zone in no_fly_zones
        }
    except NotImplementedError:
        # Start policy (e.g. ON_EVENT) not evaluable from scenario time
        # alone — best-effort, same precedent as _resolvable_span_seconds
        # skipping what it can't resolve rather than guessing.
        return []
    return [
        _no_fly_finding(mission, mission_index, zone, "orbit path")
        for zone in no_fly_zones
        if crossings_by_zone[zone.id]
    ]


def _no_fly_containment_findings(version: ScenarioVersion) -> list[ValidationFinding]:
    """Region simulation semantics (ADR-015): a mission's trajectory must
    never enter a ``NO_FLY`` zone — BLOCKING, checked at plan-time
    (publish), not runtime. Non-ORBIT templates sample each waypoint-to-
    waypoint leg at a handful of fractions (endpoints + quarters) rather
    than ``mission_evaluator.zone_crossings``'s full sampling cadence — this
    only needs a yes/no containment answer over the mission's whole
    authored span, not interval boundaries, so a coarser, bounded sample
    per leg is enough (a documented approximation, not exact-geometry
    segment/polygon intersection). ORBIT is handled separately (see
    ``_orbit_no_fly_findings``) since its waypoints don't describe the
    flown path at all.
    """
    findings: list[ValidationFinding] = []
    no_fly_zones = [z for z in version.zones if z.zone_type == _NO_FLY_ZONE_TYPE]
    if not no_fly_zones:
        return findings

    for mission_index, mission in enumerate(version.missions):
        if mission.trajectory.template == MissionTemplate.ORBIT:
            findings.extend(_orbit_no_fly_findings(mission, mission_index, no_fly_zones))
            continue

        waypoints = sorted(mission.trajectory.waypoints, key=lambda w: w.sequence_index)
        for from_wp, to_wp in zip(waypoints, waypoints[1:], strict=False):
            for zone in no_fly_zones:
                entered = any(
                    point_in_polygon(
                        _antimeridian_aware_lerp(from_wp.position, to_wp.position, fraction),
                        zone.polygon,
                    )
                    for fraction in _NO_FLY_SAMPLE_FRACTIONS
                )
                if entered:
                    findings.append(
                        _no_fly_finding(
                            mission,
                            mission_index,
                            zone,
                            f"trajectory between waypoints {from_wp.sequence_index} and "
                            f"{to_wp.sequence_index}",
                        )
                    )

    return findings


def _zone_trigger_overlap_findings(version: ScenarioVersion) -> list[ValidationFinding]:
    """``zone_trigger`` overlap cases checkable without a compile-time
    ``duration_s`` (ADR-017/ADR-018; ``_resolvable_span_seconds`` already
    documents why zone_trigger emissions are otherwise skipped from overlap
    detection entirely). Overlap between a zone_trigger emission and a
    manually-timed non-looping one is still out of scope — that needs a
    time horizon this module doesn't have — see ADR-018.

    1. Two zone_trigger emissions on the same link referencing the same
       ``zone_id`` activate/deactivate in lockstep, so they always overlap
       (BLOCKING — provably certain).
    2. A zone_trigger emission coexisting on a link with a ``loop=True``
       emission always overlaps it — a looping emission is active for the
       entire scenario by definition (BLOCKING — provably certain;
       ``_resolvable_span_seconds`` already treats a loop as open-ended).
    3. Two zone_trigger emissions on the same link referencing *different*
       zones whose polygons overlap in space (``rogue.domain.geometry.
       polygons_intersect``, ADR-018) — WARNING, not BLOCKING: unlike cases
       1-2, this is a *possible* overlap, not a certain one. Whether the
       emissions are ever simultaneously active depends on the mission's
       actual trajectory, which this geometry-only check deliberately
       doesn't evaluate (same shape as ``rogue.spectrum.occupancy``'s
       ``spectral_overlap`` finding: advisory, since intentional/never-
       actually-realized overlap is legal per CLAUDE.md rule 5).
    """
    findings: list[ValidationFinding] = []
    zones_by_id = {zone.id: zone for zone in version.zones}

    for mission_index, mission in enumerate(version.missions):
        for link_index, link in enumerate(mission.rf_links):
            link_path = f"missions[{mission_index}].rf_links[{link_index}]"
            zone_triggered = [
                (i, e) for i, e in enumerate(link.emissions) if e.zone_trigger is not None
            ]
            has_loop = any(e.loop for e in link.emissions)

            if has_loop:
                for emission_index, _emission in zone_triggered:
                    findings.append(
                        ValidationFinding(
                            severity=ValidationSeverity.BLOCKING,
                            code="zone_trigger_overlaps_loop",
                            message=(
                                f"emission {emission_index}'s zone_trigger always overlaps "
                                "this RfLink's looping emission, which is active for the "
                                "entire scenario"
                            ),
                            path=f"{link_path}.emissions[{emission_index}]",
                        )
                    )

            seen_zone_ids: dict[UUID, int] = {}
            for emission_index, emission in zone_triggered:
                assert emission.zone_trigger is not None  # guaranteed by the filter above
                zone_id = emission.zone_trigger.zone_id
                prev_index = seen_zone_ids.get(zone_id)
                if prev_index is not None:
                    findings.append(
                        ValidationFinding(
                            severity=ValidationSeverity.BLOCKING,
                            code="zone_trigger_duplicate_zone",
                            message=(
                                f"emissions {prev_index} and {emission_index} on this RfLink "
                                f"both trigger on zone {zone_id} and always overlap"
                            ),
                            path=f"{link_path}.emissions[{emission_index}]",
                        )
                    )
                else:
                    seen_zone_ids[zone_id] = emission_index

            for (i_index, i_emission), (j_index, j_emission) in combinations(zone_triggered, 2):
                assert i_emission.zone_trigger is not None  # guaranteed by the filter above
                assert j_emission.zone_trigger is not None
                i_zone_id = i_emission.zone_trigger.zone_id
                j_zone_id = j_emission.zone_trigger.zone_id
                if i_zone_id == j_zone_id:
                    continue  # already reported as zone_trigger_duplicate_zone above
                i_zone = zones_by_id.get(i_zone_id)
                j_zone = zones_by_id.get(j_zone_id)
                if i_zone is None or j_zone is None:
                    continue  # unresolvable reference is _zone_reference_findings's job
                if polygons_intersect(i_zone.polygon, j_zone.polygon):
                    findings.append(
                        ValidationFinding(
                            severity=ValidationSeverity.WARNING,
                            code="zone_trigger_zones_may_overlap",
                            message=(
                                f"emissions {i_index} and {j_index} on this RfLink trigger on "
                                f"zones {i_zone_id} and {j_zone_id}, whose polygons overlap in "
                                "space — they may be simultaneously active depending on the "
                                "mission's actual trajectory (not evaluated here)"
                            ),
                            path=f"{link_path}.emissions[{j_index}]",
                        )
                    )

    return findings


def validate_scenario_version(version: ScenarioVersion) -> list[ValidationFinding]:
    """Run cross-entity consistency checks over a ScenarioVersion.

    Structural invariants already enforced by pydantic validators on the
    individual models are not repeated here.
    """
    findings: list[ValidationFinding] = list(_coherent_group_findings(version))
    findings.extend(_zone_reference_findings(version))
    findings.extend(_no_fly_containment_findings(version))
    findings.extend(_zone_trigger_overlap_findings(version))

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
