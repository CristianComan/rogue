"""Geodetic distance/bearing helpers shared by receiver-geometry code.

Direct ports of ``frontend/src/domain/geojson.ts``'s ``haversineDistanceMeters``/
``bearingDegrees`` (same formulas, same simplifications — a standard
haversine great-circle approximation, not a geodesic/ellipsoidal
calculation) so backend-computed geometry (rogue.compiler.coherent_groups)
and the frontend's Doppler view agree on the same numbers for the same
inputs.
"""

from __future__ import annotations

import math

from rogue.domain.common import GeoPoint

EARTH_RADIUS_M = 6_371_000.0
SPEED_OF_LIGHT_MPS = 299_792_458.0


def haversine_distance_m(a: GeoPoint, b: GeoPoint) -> float:
    """Great-circle surface distance between two points, in meters."""
    lat1, lat2 = math.radians(a.latitude), math.radians(b.latitude)
    d_lat = lat2 - lat1
    d_lon = math.radians(b.longitude - a.longitude)
    h = math.sin(d_lat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(d_lon / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(h))


def bearing_degrees(a: GeoPoint, b: GeoPoint) -> float:
    """Initial bearing from ``a`` to ``b``, in degrees, 0-360 (0 = north)."""
    lat1, lat2 = math.radians(a.latitude), math.radians(b.latitude)
    d_lon = math.radians(b.longitude - a.longitude)
    y = math.sin(d_lon) * math.cos(lat2)
    x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(d_lon)
    return (math.degrees(math.atan2(y, x)) + 360) % 360


def horizontal_los_unit_vector(from_point: GeoPoint, to_point: GeoPoint) -> tuple[float, float]:
    """(east, north) unit vector of the horizontal line-of-sight bearing from ``from_point``
    to ``to_point`` — the local ENU frame ``Receiver.element_local_offset_m`` is expressed in.

    Elevation/altitude is intentionally not modelled here (a horizontal-only
    approximation): the up component of a phase/delay projection is treated
    as zero, documented as a known simplification of this first slice (see
    ADR-012).
    """
    bearing_rad = math.radians(bearing_degrees(from_point, to_point))
    return math.sin(bearing_rad), math.cos(bearing_rad)
