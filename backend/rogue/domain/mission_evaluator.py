"""Deterministic mission-position evaluation at an arbitrary scenario time.

A narrow Python port of ``frontend/src/domain/missionEvaluator.ts``'s
``evaluateMissionState``, covering only what
``rogue.compiler.coherent_groups`` needs — the transmitter's horizontal
position ``p_tx(t)`` for TDOA/AOA_DOA phase/delay computation — not the
full mission-preview feature set (velocity/heading/phase/completion
fraction). ``rogue.domain.mission``'s own module docstring flags mission-
time evaluation as intentionally deferred to "the mission engine," which so
far only exists on the frontend (also noted in
``rogue.spectrum.occupancy``'s module docstring); this is the first
backend port, scoped to WAYPOINT_TRANSIT/SCRIPTED_TRACK (arc-length
interpolation) and ORBIT (angular motion) — the templates a coherent-group
scenario would realistically use for a receiver-stimulation demo. Other
templates raise ``NotImplementedError`` naming the gap explicitly, matching
the frontend evaluator's own precedent of documenting per-template
coverage in its module docstring.
"""

from __future__ import annotations

import math

from rogue.domain.common import GeoPoint, GeoPolygon
from rogue.domain.geometry import EARTH_RADIUS_M, haversine_distance_m, point_in_polygon
from rogue.domain.mission import (
    DroneMission,
    MissionStartPolicy,
    MissionTemplate,
    Trajectory,
    Waypoint,
)

_ARC_LENGTH_TEMPLATES = {MissionTemplate.WAYPOINT_TRANSIT, MissionTemplate.SCRIPTED_TRACK}
_DEFAULT_ORBIT_RADIUS_M = 100.0

# Region-crossing sampling cadence (region simulation semantics, ADR-015) —
# same ~1s cadence rogue.compiler.coherent_groups.compute_doppler_schedule
# already uses for Doppler sampling: a documented granularity choice, not a
# claim of exact crossing-instant precision. Capped generously above that
# module's own 61-sample-per-window cap since zone_crossings scans a whole
# compile horizon up front (rogue.compiler.windows._boundary_seconds), not
# one window at a time.
ZONE_CROSSING_STEP_SECONDS = 1.0
MAX_ZONE_CROSSING_SAMPLES = 3601


def evaluate_mission_start_seconds(mission: DroneMission) -> float:
    """Mission start, in scenario-time seconds.

    Raises NotImplementedError for ON_EVENT/MANUAL start policies, which
    (per missionEvaluator.ts's same documented gap) aren't evaluable from
    scenario time alone.
    """
    if mission.start_policy == MissionStartPolicy.AT_SCENARIO_START:
        return 0.0
    if mission.start_policy == MissionStartPolicy.AT_TIME_OFFSET:
        assert mission.start_time_offset is not None  # enforced by DroneMission's own validator
        return mission.start_time_offset.total_seconds()
    raise NotImplementedError(
        f"{mission.start_policy} mission start is not evaluable from scenario time alone"
    )


def _ordered_waypoints(trajectory: Trajectory) -> list[Waypoint]:
    return sorted(trajectory.waypoints, key=lambda w: w.sequence_index)


def _leg_speed_mps(trajectory: Trajectory, from_waypoint: Waypoint) -> float:
    if from_waypoint.speed_mps is not None:
        return from_waypoint.speed_mps
    return trajectory.default_speed_mps


def _lerp_position(a: GeoPoint, b: GeoPoint, fraction: float) -> GeoPoint:
    lon = a.longitude + (b.longitude - a.longitude) * fraction
    lat = a.latitude + (b.latitude - a.latitude) * fraction
    return GeoPoint(coordinates=(lon, lat))


def _evaluate_arc_length_position(trajectory: Trajectory, mission_time_s: float) -> GeoPoint:
    """Non-looping arc-length interpolation over the authored waypoints.

    Mirrors missionEvaluator.ts's buildLegSchedule plus the "before start"/
    "holding"/"en_route"/"one-shot final hold" branches of
    evaluateMissionState, minus everything not needed for position alone.
    """
    ordered = _ordered_waypoints(trajectory)
    if mission_time_s < 0:
        return ordered[0].position

    cursor = 0.0
    for from_wp, to_wp in zip(ordered, ordered[1:], strict=False):
        hold_start = cursor
        hold_end = hold_start + from_wp.hold_seconds
        if mission_time_s < hold_end:
            return from_wp.position
        distance_m = haversine_distance_m(from_wp.position, to_wp.position)
        speed_mps = _leg_speed_mps(trajectory, from_wp)
        transit_s = distance_m / speed_mps if speed_mps > 0 else 0.0
        leg_end = hold_end + transit_s
        if mission_time_s < leg_end:
            fraction = (mission_time_s - hold_end) / transit_s if transit_s > 0 else 0.0
            return _lerp_position(from_wp.position, to_wp.position, fraction)
        cursor = leg_end

    return ordered[-1].position


def _orbit_center_and_radius(trajectory: Trajectory) -> tuple[GeoPoint, float]:
    ordered = _ordered_waypoints(trajectory)
    radius_m = trajectory.template_parameters.get("radius_m", _DEFAULT_ORBIT_RADIUS_M)
    return ordered[0].position, radius_m


def _point_on_circle(center: GeoPoint, radius_m: float, angle_deg: float) -> GeoPoint:
    """Local equirectangular approximation — matches geojson.ts:pointOnCircle exactly."""
    angle_rad = math.radians(angle_deg)
    lat_rad = math.radians(center.latitude)
    d_lat = (radius_m * math.sin(angle_rad) / EARTH_RADIUS_M) * (180.0 / math.pi)
    cos_lat = math.cos(lat_rad)
    d_lon = (
        (radius_m * math.cos(angle_rad) / (EARTH_RADIUS_M * cos_lat)) * (180.0 / math.pi)
        if cos_lat != 0
        else 0.0
    )
    return GeoPoint(coordinates=(center.longitude + d_lon, center.latitude + d_lat))


def _evaluate_orbit_position(trajectory: Trajectory, mission_time_s: float) -> GeoPoint:
    center, radius_m = _orbit_center_and_radius(trajectory)
    speed_mps = trajectory.default_speed_mps
    angular_velocity_deg_per_s = (speed_mps / radius_m) * (180.0 / math.pi) if radius_m > 0 else 0.0
    angle_deg = (mission_time_s * angular_velocity_deg_per_s) % 360.0
    return _point_on_circle(center, radius_m, angle_deg)


def orbit_period_seconds(trajectory: Trajectory) -> float:
    """Time for one full ORBIT lap, or ``0.0`` for a degenerate (zero-radius
    or zero-speed) orbit that never moves.

    An ORBIT mission loops indefinitely and retraces the same circle every
    lap, so a caller that needs to observe the *whole* geometric path (e.g.
    ``rogue.domain.validation``'s ``NO_FLY`` containment check, which has no
    other natural time bound for a template that never "finishes") only
    needs to sample one period via ``zone_crossings`` — matches
    ``_evaluate_orbit_position``'s own angular-velocity formula.
    """
    _, radius_m = _orbit_center_and_radius(trajectory)
    speed_mps = trajectory.default_speed_mps
    if radius_m <= 0 or speed_mps <= 0:
        return 0.0
    return 2 * math.pi * radius_m / speed_mps


def evaluate_mission_position(mission: DroneMission, at_seconds: float) -> GeoPoint:
    """The drone's horizontal position at scenario time ``at_seconds``.

    Covers MissionTemplate.WAYPOINT_TRANSIT/SCRIPTED_TRACK (arc-length
    interpolation) and ORBIT (angular motion, loops indefinitely) — see
    module docstring for why other templates raise NotImplementedError
    instead of guessing.
    """
    start_seconds = evaluate_mission_start_seconds(mission)
    trajectory = mission.trajectory
    if at_seconds < start_seconds:
        return _ordered_waypoints(trajectory)[0].position

    mission_time_s = at_seconds - start_seconds
    if trajectory.template == MissionTemplate.ORBIT:
        return _evaluate_orbit_position(trajectory, mission_time_s)
    if trajectory.template in _ARC_LENGTH_TEMPLATES:
        return _evaluate_arc_length_position(trajectory, mission_time_s)

    raise NotImplementedError(
        f"mission position evaluation for template {trajectory.template!r} is not yet "
        "ported to the backend (frontend/src/domain/missionEvaluator.ts covers more "
        "templates; this backend port is scoped to what coherent-group phase/delay "
        "computation needs — see rogue.compiler.coherent_groups)"
    )


def zone_crossings(
    mission: DroneMission, polygon: GeoPolygon, window_start: float, window_end: float
) -> list[tuple[float, float]]:
    """Sub-intervals of ``[window_start, window_end)`` where ``mission``'s
    position is inside ``polygon`` (region simulation semantics, ADR-015).

    Samples ``evaluate_mission_position`` at ``ZONE_CROSSING_STEP_SECONDS``
    cadence and reports interval boundaries at that sampled granularity —
    the same documented-approximation shape as ``compute_doppler_schedule``,
    not sub-sample-interpolated crossing instants. Serves both
    ``no_transmit`` gating (mute *during* the returned intervals) and
    ``trigger`` emission timing (active *during* them) — one primitive,
    reused two ways, rather than two separate implementations.

    Propagates ``NotImplementedError`` from ``evaluate_mission_position``
    unchanged (an unsupported mission template) — callers already handle
    that the same way ``rogue.compiler.coherent_groups`` does for Doppler/
    phase/delay.
    """
    span = max(0.0, window_end - window_start)
    sample_count = max(
        2, min(MAX_ZONE_CROSSING_SAMPLES, math.ceil(span / ZONE_CROSSING_STEP_SECONDS) + 1)
    )
    samples: list[tuple[float, bool]] = []
    for i in range(sample_count):
        t = window_start + (span * i / (sample_count - 1) if sample_count > 1 else 0.0)
        position = evaluate_mission_position(mission, t)
        samples.append((t, point_in_polygon(position, polygon)))

    intervals: list[tuple[float, float]] = []
    interval_start: float | None = None
    for t, inside in samples:
        if inside and interval_start is None:
            interval_start = t
        elif not inside and interval_start is not None:
            intervals.append((interval_start, t))
            interval_start = None
    if interval_start is not None:
        intervals.append((interval_start, window_end))
    return intervals
