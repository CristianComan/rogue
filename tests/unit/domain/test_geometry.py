"""Tests for haversine distance/bearing geometry helpers."""

from __future__ import annotations

import math

import pytest

from rogue.domain.common import GeoPoint, GeoPolygon
from rogue.domain.geometry import (
    EARTH_RADIUS_M,
    bearing_degrees,
    haversine_distance_m,
    horizontal_los_unit_vector,
    point_in_polygon,
)


def point(lon: float, lat: float) -> GeoPoint:
    return GeoPoint(coordinates=(lon, lat))


SQUARE = GeoPolygon(coordinates=[[(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0), (0.0, 0.0)]])


def test_point_in_polygon_true_for_interior_point() -> None:
    assert point_in_polygon(point(0.5, 0.5), SQUARE) is True


def test_point_in_polygon_false_for_exterior_point() -> None:
    assert point_in_polygon(point(2.0, 2.0), SQUARE) is False


def test_point_in_polygon_false_just_outside_edge() -> None:
    assert point_in_polygon(point(-0.001, 0.5), SQUARE) is False


def test_point_in_polygon_true_just_inside_edge() -> None:
    assert point_in_polygon(point(0.001, 0.5), SQUARE) is True


def test_point_in_polygon_handles_3d_ring_coordinates() -> None:
    # GeoPolygon rings may carry altitude (GeoPosition3D); containment
    # should ignore the extra element rather than fail to unpack.
    square_3d = GeoPolygon(
        coordinates=[
            [
                (0.0, 0.0, 10.0),
                (1.0, 0.0, 10.0),
                (1.0, 1.0, 10.0),
                (0.0, 1.0, 10.0),
                (0.0, 0.0, 10.0),
            ]
        ]
    )
    assert point_in_polygon(point(0.5, 0.5), square_3d) is True
    assert point_in_polygon(point(2.0, 2.0), square_3d) is False


def test_haversine_distance_to_self_is_zero() -> None:
    p = point(13.4, 52.5)
    assert haversine_distance_m(p, p) == pytest.approx(0.0, abs=1e-6)


def test_haversine_distance_matches_meridian_arc_for_same_longitude() -> None:
    # Same longitude: haversine reduces exactly to R * delta_lat_radians.
    a = point(0.0, 0.0)
    b = point(0.0, 1.0)
    expected = EARTH_RADIUS_M * math.radians(1.0)
    assert haversine_distance_m(a, b) == pytest.approx(expected, rel=1e-9)


def test_bearing_due_north_is_zero() -> None:
    assert bearing_degrees(point(0.0, 0.0), point(0.0, 1.0)) == pytest.approx(0.0, abs=1e-9)


def test_bearing_due_east_along_equator_is_ninety() -> None:
    assert bearing_degrees(point(0.0, 0.0), point(1.0, 0.0)) == pytest.approx(90.0, abs=1e-9)


def test_horizontal_los_unit_vector_due_north() -> None:
    east, north = horizontal_los_unit_vector(point(0.0, 0.0), point(0.0, 1.0))
    assert east == pytest.approx(0.0, abs=1e-9)
    assert north == pytest.approx(1.0, abs=1e-9)


def test_horizontal_los_unit_vector_due_east() -> None:
    east, north = horizontal_los_unit_vector(point(0.0, 0.0), point(1.0, 0.0))
    assert east == pytest.approx(1.0, abs=1e-9)
    assert north == pytest.approx(0.0, abs=1e-9)
