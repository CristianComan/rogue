"""Tests for Platform/DroneMission/Trajectory/Waypoint entities."""

from __future__ import annotations

from datetime import timedelta

import pytest
from factories import drone_mission_kwargs, trajectory_kwargs, waypoint
from pydantic import ValidationError

from rogue.domain.mission import DroneMission, MissionStartPolicy, Trajectory


def test_trajectory_requires_at_least_two_waypoints() -> None:
    with pytest.raises(ValidationError):
        Trajectory(**trajectory_kwargs(waypoints=[waypoint(0, 13.4, 52.5)]))


def test_trajectory_rejects_non_ascending_sequence_indices() -> None:
    with pytest.raises(ValidationError):
        Trajectory(
            **trajectory_kwargs(waypoints=[waypoint(1, 13.4, 52.5), waypoint(0, 13.45, 52.53)])
        )


def test_trajectory_rejects_duplicate_sequence_indices() -> None:
    with pytest.raises(ValidationError):
        Trajectory(
            **trajectory_kwargs(waypoints=[waypoint(0, 13.4, 52.5), waypoint(0, 13.45, 52.53)])
        )


def test_trajectory_to_geojson_linestring_orders_by_sequence() -> None:
    trajectory = Trajectory(**trajectory_kwargs())
    geojson = trajectory.to_geojson_linestring()

    assert geojson["type"] == "LineString"
    assert len(geojson["coordinates"]) == 2  # type: ignore[arg-type]


def test_mission_at_time_offset_requires_offset_value() -> None:
    with pytest.raises(ValidationError):
        DroneMission(
            **drone_mission_kwargs(
                start_policy=MissionStartPolicy.AT_TIME_OFFSET, start_time_offset=None
            )
        )


def test_mission_scenario_start_rejects_offset_value() -> None:
    with pytest.raises(ValidationError):
        DroneMission(
            **drone_mission_kwargs(
                start_policy=MissionStartPolicy.AT_SCENARIO_START,
                start_time_offset=timedelta(seconds=1),
            )
        )


def test_valid_mission_round_trips() -> None:
    mission = DroneMission(**drone_mission_kwargs())
    restored = DroneMission.model_validate(mission.model_dump(mode="json"))
    assert restored.name == mission.name
    assert len(restored.trajectory.waypoints) == 2
