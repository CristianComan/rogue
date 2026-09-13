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

from rogue.domain.common import GeoPoint, GeoPolygon

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


def point_in_polygon(point: GeoPoint, polygon: GeoPolygon) -> bool:
    """Ray-casting point-in-polygon test against ``polygon``'s exterior ring
    (``GeoPolygon``'s own docstring: "first ring is the exterior boundary" —
    interior rings/holes are not modelled, matching every other consumer of
    this type). Operates directly on (lon, lat) as a planar ring, the same
    simplification MapLibre's own rendering already makes for these
    zone/area polygons — adequate at the scenario-authoring scale this
    system operates at (city-block to city-scale areas), not a claim of
    geodesic correctness for very large or pole-spanning polygons.
    """
    ring = polygon.coordinates[0]
    x, y = point.longitude, point.latitude
    inside = False
    for (x1, y1, *_), (x2, y2, *_) in zip(ring, ring[1:], strict=False):
        if (y1 > y) != (y2 > y):
            x_intersect = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
            if x < x_intersect:
                inside = not inside
    return inside


def _orientation(
    a: tuple[float, float], b: tuple[float, float], c: tuple[float, float]
) -> float:
    """Signed area of triangle a-b-c: >0 counter-clockwise, <0 clockwise, 0 collinear."""
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _on_segment(a: tuple[float, float], b: tuple[float, float], p: tuple[float, float]) -> bool:
    """Whether collinear point ``p`` lies within segment ``a``-``b``'s bounding box."""
    return min(a[0], b[0]) <= p[0] <= max(a[0], b[0]) and min(a[1], b[1]) <= p[1] <= max(a[1], b[1])


def _segments_intersect(
    p1: tuple[float, float],
    p2: tuple[float, float],
    p3: tuple[float, float],
    p4: tuple[float, float],
) -> bool:
    """Standard orientation-based segment intersection test, including the
    collinear-overlap and touching-endpoint cases (both treated as
    intersecting — the conservative choice for this module's use, flagging
    a possible conflict rather than silently ruling one out).
    """
    o1, o2 = _orientation(p1, p2, p3), _orientation(p1, p2, p4)
    o3, o4 = _orientation(p3, p4, p1), _orientation(p3, p4, p2)

    if (o1 > 0) != (o2 > 0) and (o3 > 0) != (o4 > 0):
        return True

    if o1 == 0 and _on_segment(p1, p2, p3):
        return True
    if o2 == 0 and _on_segment(p1, p2, p4):
        return True
    if o3 == 0 and _on_segment(p3, p4, p1):
        return True
    return bool(o4 == 0 and _on_segment(p3, p4, p2))


def polygons_intersect(a: GeoPolygon, b: GeoPolygon) -> bool:
    """Whether ``a`` and ``b``'s exterior rings overlap (share any area or
    boundary), including one polygon fully containing the other.

    Same conventions as ``point_in_polygon``: exterior ring only (interior
    rings/holes not modelled), planar (lon, lat) treatment rather than
    geodesic — adequate at scenario-authoring scale, not a claim of
    correctness for very large or pole-spanning polygons. Handles arbitrary
    simple (non-self-intersecting) polygons, including concave ones: first
    checks every edge pair for a crossing (which also catches partial
    overlap and touching edges/vertices), then falls back to a single
    vertex-in-polygon check each way to catch the case where one polygon
    fully contains the other with no edges crossing at all.
    """
    ring_a = [(p[0], p[1]) for p in a.coordinates[0]]
    ring_b = [(p[0], p[1]) for p in b.coordinates[0]]

    for a1, a2 in zip(ring_a, ring_a[1:], strict=False):
        for b1, b2 in zip(ring_b, ring_b[1:], strict=False):
            if _segments_intersect(a1, a2, b1, b2):
                return True

    a_point = GeoPoint(coordinates=ring_a[0])
    b_point = GeoPoint(coordinates=ring_b[0])
    return point_in_polygon(a_point, b) or point_in_polygon(b_point, a)


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
