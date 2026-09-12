"""Tests for the backend's narrow mission-position evaluator port.

Mirrors frontend/src/domain/missionEvaluator.test.ts's straight-leg and
orbit cases for the templates this backend port actually covers.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest

from rogue.domain.common import GeoPoint, GeoPolygon
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
from rogue.domain.mission_evaluator import (
    evaluate_mission_position,
    orbit_period_seconds,
    zone_crossings,
)

PLATFORM = Platform(name="test-quad", category=PlatformCategory.MULTIROTOR, max_speed_mps=20.0)


def waypoint(sequence_index: int, lon: float, lat: float, hold_seconds: float = 0.0) -> Waypoint:
    return Waypoint(
        sequence_index=sequence_index,
        position=GeoPoint(coordinates=(lon, lat)),
        altitude_m=100.0,
        altitude_reference=AltitudeReference.AGL,
        hold_seconds=hold_seconds,
    )


def mission(trajectory: Trajectory, **overrides: Any) -> DroneMission:
    kwargs: dict[str, Any] = {
        "name": "test-mission",
        "platform": PLATFORM,
        "trajectory": trajectory,
        "start_policy": MissionStartPolicy.AT_SCENARIO_START,
        "rf_links": [],
    }
    kwargs.update(overrides)
    return DroneMission(**kwargs)


# A straight ~1000m-ish leg due north, easy to reason about (same fixture
# shape as missionEvaluator.test.ts's STRAIGHT_LEG).
STRAIGHT_LEG = Trajectory(
    template=MissionTemplate.WAYPOINT_TRANSIT,
    waypoints=[waypoint(0, 13.4, 52.5), waypoint(1, 13.4, 52.509)],
    default_speed_mps=10.0,
)


def test_position_before_start_is_first_waypoint() -> None:
    m = mission(
        STRAIGHT_LEG,
        start_policy=MissionStartPolicy.AT_TIME_OFFSET,
        start_time_offset=timedelta(seconds=100),
    )
    position = evaluate_mission_position(m, 0.0)
    assert position.longitude == pytest.approx(13.4)
    assert position.latitude == pytest.approx(52.5)


def test_position_at_mission_start_is_first_waypoint() -> None:
    position = evaluate_mission_position(mission(STRAIGHT_LEG), 0.0)
    assert position.longitude == pytest.approx(13.4)
    assert position.latitude == pytest.approx(52.5)


def test_position_holds_at_first_waypoint_during_hold_seconds() -> None:
    trajectory = Trajectory(
        template=MissionTemplate.WAYPOINT_TRANSIT,
        waypoints=[waypoint(0, 13.4, 52.5, hold_seconds=30.0), waypoint(1, 13.4, 52.509)],
        default_speed_mps=10.0,
    )
    position = evaluate_mission_position(mission(trajectory), 15.0)
    assert position.longitude == pytest.approx(13.4)
    assert position.latitude == pytest.approx(52.5)


def test_position_interpolates_mid_leg() -> None:
    # ~1000m leg at 10 m/s takes ~100s; halfway through, latitude should be
    # roughly halfway between the two waypoints.
    position = evaluate_mission_position(mission(STRAIGHT_LEG), 50.0)
    assert 52.5 < position.latitude < 52.509


def test_position_clamps_at_final_waypoint_past_transit() -> None:
    position = evaluate_mission_position(mission(STRAIGHT_LEG), 10_000.0)
    assert position.longitude == pytest.approx(13.4)
    assert position.latitude == pytest.approx(52.509)


def test_scripted_track_uses_the_same_arc_length_interpolation() -> None:
    scripted = Trajectory(
        template=MissionTemplate.SCRIPTED_TRACK,
        waypoints=[waypoint(0, 13.4, 52.5), waypoint(1, 13.4, 52.509)],
        default_speed_mps=10.0,
    )
    position = evaluate_mission_position(mission(scripted), 0.0)
    assert position.longitude == pytest.approx(13.4)
    assert position.latitude == pytest.approx(52.5)


ORBIT = Trajectory(
    template=MissionTemplate.ORBIT,
    waypoints=[waypoint(0, 13.4, 52.5), waypoint(1, 13.41, 52.5)],
    default_speed_mps=10.0,
    template_parameters={"radius_m": 100.0},
)


def test_orbit_position_at_t_zero_is_east_of_center() -> None:
    position = evaluate_mission_position(mission(ORBIT), 0.0)
    center = ORBIT.waypoints[0].position
    assert position.longitude > center.longitude
    assert position.latitude == pytest.approx(center.latitude, abs=1e-6)


def test_orbit_loops_indefinitely() -> None:
    # A full period later, position should return to (approximately) the start.
    period_s = orbit_period_seconds(ORBIT)
    start = evaluate_mission_position(mission(ORBIT), 0.0)
    after_one_period = evaluate_mission_position(mission(ORBIT), period_s)
    assert after_one_period.longitude == pytest.approx(start.longitude, abs=1e-6)
    assert after_one_period.latitude == pytest.approx(start.latitude, abs=1e-6)


def test_orbit_period_seconds_matches_circumference_over_speed() -> None:
    expected = 2 * 3.141592653589793 * 100.0 / 10.0
    assert orbit_period_seconds(ORBIT) == pytest.approx(expected)


def test_orbit_period_seconds_is_zero_for_degenerate_orbit() -> None:
    zero_radius = Trajectory(
        template=MissionTemplate.ORBIT,
        waypoints=[waypoint(0, 13.4, 52.5), waypoint(1, 13.41, 52.5)],
        default_speed_mps=10.0,
        template_parameters={"radius_m": 0.0},
    )
    assert orbit_period_seconds(zero_radius) == 0.0


def test_unsupported_template_raises_not_implemented() -> None:
    racetrack = Trajectory(
        template=MissionTemplate.RACETRACK,
        waypoints=[waypoint(0, 13.4, 52.5), waypoint(1, 13.41, 52.5)],
        default_speed_mps=10.0,
    )
    with pytest.raises(NotImplementedError):
        evaluate_mission_position(mission(racetrack), 0.0)


def test_on_event_start_policy_raises_not_implemented() -> None:
    m = mission(STRAIGHT_LEG, start_policy=MissionStartPolicy.ON_EVENT)
    with pytest.raises(NotImplementedError):
        evaluate_mission_position(m, 0.0)


# Straddles the middle third of STRAIGHT_LEG's ~100s transit (see
# test_position_interpolates_mid_leg): the mission enters partway through
# the window and exits before the end, giving one bounded interior interval.
MID_LEG_ZONE = GeoPolygon(
    coordinates=[
        [(13.39, 52.503), (13.41, 52.503), (13.41, 52.506), (13.39, 52.506), (13.39, 52.503)]
    ]
)


def test_zone_crossings_reports_no_interval_when_never_inside() -> None:
    far_away_zone = GeoPolygon(
        coordinates=[[(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0), (0.0, 0.0)]]
    )
    intervals = zone_crossings(mission(STRAIGHT_LEG), far_away_zone, 0.0, 100.0)
    assert intervals == []


def test_zone_crossings_reports_bounded_interior_interval() -> None:
    intervals = zone_crossings(mission(STRAIGHT_LEG), MID_LEG_ZONE, 0.0, 100.0)
    assert len(intervals) == 1
    start, end = intervals[0]
    assert 0.0 < start < end < 100.0


def test_zone_crossings_open_ended_interval_extends_to_window_end() -> None:
    # A polygon covering the tail of the leg: mission is still inside at
    # window_end, so the interval should be reported as extending to it
    # rather than being dropped for lacking an observed exit sample.
    tail_zone = GeoPolygon(
        coordinates=[
            [(13.39, 52.505), (13.41, 52.505), (13.41, 52.51), (13.39, 52.51), (13.39, 52.505)]
        ]
    )
    intervals = zone_crossings(mission(STRAIGHT_LEG), tail_zone, 0.0, 100.0)
    assert len(intervals) == 1
    _start, end = intervals[0]
    assert end == 100.0


def test_zone_crossings_propagates_not_implemented_for_unsupported_template() -> None:
    racetrack = Trajectory(
        template=MissionTemplate.RACETRACK,
        waypoints=[waypoint(0, 13.4, 52.5), waypoint(1, 13.41, 52.5)],
        default_speed_mps=10.0,
    )
    with pytest.raises(NotImplementedError):
        zone_crossings(mission(racetrack), MID_LEG_ZONE, 0.0, 100.0)
