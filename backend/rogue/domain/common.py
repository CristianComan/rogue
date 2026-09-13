"""Shared base types for the ROGUE scenario domain model.

Every domain entity is built on ``RogueModel``/``FrozenRogueModel`` so that
identifiers, timestamps and GeoJSON-shaped geometry are represented
consistently across scenarios, missions, RF links and receivers. See
docs/architecture/domain-model.md section 5 for the versioning/immutability
rules these types support.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


class RogueModel(BaseModel):
    """Base for mutable domain models: unknown fields are rejected."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class FrozenRogueModel(RogueModel):
    """Base for immutable domain models (e.g. published ScenarioVersion)."""

    model_config = ConfigDict(extra="forbid", frozen=True)


def new_id() -> UUID:
    """Generate a new domain entity identifier."""
    return uuid4()


def utc_now() -> datetime:
    """Current time as a UTC-aware timestamp."""
    return datetime.now(UTC)


class IdentifiedMixin(RogueModel):
    """Adds a UUID identity, per CLAUDE.md coding rule: UUIDs where defined."""

    id: UUID = Field(default_factory=new_id)


class TimestampedMixin(RogueModel):
    """Adds UTC-aware created/updated timestamps."""

    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    @field_validator("created_at", "updated_at")
    @classmethod
    def _require_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("timestamps must be timezone-aware (UTC)")
        return value.astimezone(UTC)


Longitude = Annotated[float, Field(ge=-180.0, le=180.0)]
Latitude = Annotated[float, Field(ge=-90.0, le=90.0)]

# A GeoJSON position is [lon, lat] or [lon, lat, altitude_m], WGS84.
GeoPosition2D = tuple[Longitude, Latitude]
GeoPosition3D = tuple[Longitude, Latitude, float]


class GeoPoint(RogueModel):
    """Minimal GeoJSON Point: WGS84 [lon, lat] or [lon, lat, alt_m]."""

    type: Literal["Point"] = "Point"
    coordinates: GeoPosition2D | GeoPosition3D

    @property
    def longitude(self) -> float:
        return self.coordinates[0]

    @property
    def latitude(self) -> float:
        return self.coordinates[1]

    @property
    def altitude_m(self) -> float | None:
        return self.coordinates[2] if len(self.coordinates) == 3 else None


class GeoLineString(RogueModel):
    """Minimal GeoJSON LineString."""

    type: Literal["LineString"] = "LineString"
    coordinates: list[GeoPosition2D | GeoPosition3D]

    @field_validator("coordinates")
    @classmethod
    def _min_two_points(
        cls, value: list[GeoPosition2D | GeoPosition3D]
    ) -> list[GeoPosition2D | GeoPosition3D]:
        if len(value) < 2:
            raise ValueError("LineString requires at least two coordinates")
        return value


class GeoPolygon(RogueModel):
    """Minimal GeoJSON Polygon: first ring is the exterior boundary."""

    type: Literal["Polygon"] = "Polygon"
    coordinates: list[list[GeoPosition2D | GeoPosition3D]]

    @field_validator("coordinates")
    @classmethod
    def _closed_rings(
        cls, value: list[list[GeoPosition2D | GeoPosition3D]]
    ) -> list[list[GeoPosition2D | GeoPosition3D]]:
        if not value:
            raise ValueError("Polygon requires at least one ring")
        for ring in value:
            if len(ring) < 4:
                raise ValueError("each Polygon ring requires at least four positions")
            if ring[0][:2] != ring[-1][:2]:
                raise ValueError("each Polygon ring must be closed (first == last position)")
        return value
