"""Tests for haversine distance/bearing geometry helpers."""

from __future__ import annotations

import math

import pytest

from rogue.domain.common import GeoPoint
from rogue.domain.geometry import (
    EARTH_RADIUS_M,
    bearing_degrees,
    haversine_distance_m,
    horizontal_los_unit_vector,
)


def point(lon: float, lat: float) -> GeoPoint:
    return GeoPoint(coordinates=(lon, lat))


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
