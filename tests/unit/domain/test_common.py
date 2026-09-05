"""Tests for shared base types: geometry bounds and UTC timestamp handling."""

from __future__ import annotations

from datetime import datetime

import pytest
from pydantic import ValidationError

from rogue.domain.common import GeoLineString, GeoPoint, GeoPolygon, TimestampedMixin


def test_geo_point_accepts_2d_and_3d() -> None:
    p2 = GeoPoint(coordinates=(13.4, 52.5))
    p3 = GeoPoint(coordinates=(13.4, 52.5, 120.0))

    assert p2.altitude_m is None
    assert p3.altitude_m == 120.0


@pytest.mark.parametrize("bad_coords", [(200.0, 10.0), (10.0, -100.0)])
def test_geo_point_rejects_out_of_range_coordinates(bad_coords: tuple[float, float]) -> None:
    with pytest.raises(ValidationError):
        GeoPoint(coordinates=bad_coords)


def test_geo_linestring_requires_two_points() -> None:
    with pytest.raises(ValidationError):
        GeoLineString(coordinates=[(13.4, 52.5)])


def test_geo_polygon_requires_closed_ring() -> None:
    with pytest.raises(ValidationError):
        GeoPolygon(coordinates=[[(0, 0), (1, 0), (1, 1), (0, 1)]])  # not closed


def test_geo_polygon_accepts_closed_ring() -> None:
    ring = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0), (0.0, 0.0)]
    polygon = GeoPolygon(coordinates=[ring])
    assert polygon.coordinates[0][0] == polygon.coordinates[0][-1]


def test_timestamped_mixin_requires_tz_aware() -> None:
    with pytest.raises(ValidationError):
        TimestampedMixin(created_at=datetime(2026, 1, 1), updated_at=datetime(2026, 1, 1))


def test_timestamped_mixin_defaults_to_utc_now() -> None:
    stamped = TimestampedMixin()
    assert stamped.created_at.tzinfo is not None
