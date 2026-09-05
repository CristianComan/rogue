"""Drone platform, trajectory and mission entities.

Deterministic evaluation of mission state at an arbitrary scenario time
(position, velocity, altitude, heading, phase, completion) is the mission
engine's job (M3, map/trajectory editor) and is intentionally not
implemented here — this feature only defines the typed, serializable
schema the engine will later consume, per docs/architecture/domain-model.md
sections 3-4 and implementation-plan.md's M1 scope.
"""

from __future__ import annotations

from datetime import timedelta
from enum import StrEnum

from pydantic import Field, field_validator, model_validator

from rogue.domain.common import GeoPoint, IdentifiedMixin, RogueModel
from rogue.domain.rf import DroneRfLink


class PlatformCategory(StrEnum):
    """Coarse airframe category."""

    MULTIROTOR = "multirotor"
    FIXED_WING = "fixed_wing"
    VTOL = "vtol"
    OTHER = "other"


class Platform(RogueModel):
    """The drone airframe flying a mission."""

    name: str
    category: PlatformCategory
    max_speed_mps: float = Field(gt=0)
    max_climb_rate_mps: float | None = Field(default=None, gt=0)
    notes: str | None = None


class MissionTemplate(StrEnum):
    """Supported mission templates (domain-model.md section 3)."""

    WAYPOINT_TRANSIT = "waypoint_transit"
    ORBIT = "orbit"
    RACETRACK = "racetrack"
    GRID_SEARCH = "grid_search"
    PERIMETER_PATROL = "perimeter_patrol"
    LOITER_THEN_DEPART = "loiter_then_depart"
    SWARM_STAGGERED_ARRIVAL = "swarm_staggered_arrival"
    SCRIPTED_TRACK = "scripted_track"


class AltitudeReference(StrEnum):
    """Vertical datum for an altitude value."""

    AGL = "agl"
    MSL = "msl"


class Waypoint(RogueModel):
    """One authored point along a trajectory; the canonical geometry source."""

    sequence_index: int = Field(ge=0)
    position: GeoPoint
    altitude_m: float
    altitude_reference: AltitudeReference = AltitudeReference.AGL
    speed_mps: float | None = Field(default=None, gt=0)
    heading_deg: float | None = Field(default=None, ge=0, lt=360)
    hold_seconds: float = Field(default=0.0, ge=0)


class Trajectory(RogueModel):
    """Waypoint-defined geometry plus timing/kinematic constraints.

    ``template_parameters`` carries template-specific numeric parameters
    (e.g. orbit radius_m, racetrack leg_length_m, grid spacing_m). A fully
    typed parameter schema per template is deferred until the mission
    engine (M3) needs to validate kinematic feasibility.
    """

    template: MissionTemplate
    waypoints: list[Waypoint]
    default_speed_mps: float = Field(gt=0)
    template_parameters: dict[str, float] = Field(default_factory=dict)

    @field_validator("waypoints")
    @classmethod
    def _at_least_two_waypoints(cls, value: list[Waypoint]) -> list[Waypoint]:
        if len(value) < 2:
            raise ValueError("a Trajectory requires at least two waypoints")
        return value

    @model_validator(mode="after")
    def _sequence_indices_ordered(self) -> Trajectory:
        indices = [w.sequence_index for w in self.waypoints]
        if indices != sorted(indices) or len(set(indices)) != len(indices):
            raise ValueError("waypoint sequence_index values must be unique and ascending")
        return self

    def to_geojson_linestring(self) -> dict[str, object]:
        """Derive a portable GeoJSON LineString from the authored waypoints."""
        coordinates = []
        for w in sorted(self.waypoints, key=lambda wp: wp.sequence_index):
            coordinates.append([w.position.longitude, w.position.latitude, w.altitude_m])
        return {"type": "LineString", "coordinates": coordinates}


class MissionStartPolicy(StrEnum):
    """When a mission begins relative to the scenario timeline."""

    AT_SCENARIO_START = "at_scenario_start"
    AT_TIME_OFFSET = "at_time_offset"
    ON_EVENT = "on_event"
    MANUAL = "manual"


class DroneMission(IdentifiedMixin):
    """A single drone's platform, trajectory and RF links within a scenario."""

    name: str
    platform: Platform
    trajectory: Trajectory
    start_policy: MissionStartPolicy = MissionStartPolicy.AT_SCENARIO_START
    start_time_offset: timedelta | None = None
    rf_links: list[DroneRfLink] = Field(default_factory=list)

    @model_validator(mode="after")
    def _start_offset_matches_policy(self) -> DroneMission:
        is_time_offset_policy = self.start_policy == MissionStartPolicy.AT_TIME_OFFSET
        if is_time_offset_policy and self.start_time_offset is None:
            raise ValueError("AT_TIME_OFFSET start_policy requires start_time_offset")
        if not is_time_offset_policy and self.start_time_offset is not None:
            raise ValueError("start_time_offset is only valid with AT_TIME_OFFSET start_policy")
        return self
