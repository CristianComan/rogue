/**
 * Geometry helpers shared by the mission evaluator and the map's trajectory
 * preview layer. Position interpolation is linear in lon/lat weighted by
 * haversine arc-length fraction — a standard, deliberately simple
 * approximation for a visualization/preview, not a geodesic navigation
 * calculation.
 */

import type { GeoLineString, GeoPosition, GeoPosition2D, Trajectory } from "./types";

const EARTH_RADIUS_M = 6_371_000;

function toRadians(deg: number): number {
  return (deg * Math.PI) / 180;
}

function toDegrees(rad: number): number {
  return (rad * 180) / Math.PI;
}

export function haversineDistanceMeters(a: GeoPosition, b: GeoPosition): number {
  const [lon1, lat1] = a;
  const [lon2, lat2] = b;
  const dLat = toRadians(lat2 - lat1);
  const dLon = toRadians(lon2 - lon1);
  const h =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(toRadians(lat1)) * Math.cos(toRadians(lat2)) * Math.sin(dLon / 2) ** 2;
  return 2 * EARTH_RADIUS_M * Math.asin(Math.sqrt(h));
}

/** Initial bearing from `a` to `b`, in degrees, 0-360 (0 = north). */
export function bearingDegrees(a: GeoPosition, b: GeoPosition): number {
  const [lon1, lat1] = a;
  const [lon2, lat2] = b;
  const y = Math.sin(toRadians(lon2 - lon1)) * Math.cos(toRadians(lat2));
  const x =
    Math.cos(toRadians(lat1)) * Math.sin(toRadians(lat2)) -
    Math.sin(toRadians(lat1)) * Math.cos(toRadians(lat2)) * Math.cos(toRadians(lon2 - lon1));
  return (toDegrees(Math.atan2(y, x)) + 360) % 360;
}

/** Linear lon/lat interpolation — fine for the short legs a mission authors. */
export function lerpPosition(a: GeoPosition, b: GeoPosition, fraction: number): GeoPosition2D {
  const [lon1, lat1] = a;
  const [lon2, lat2] = b;
  return [lon1 + (lon2 - lon1) * fraction, lat1 + (lat2 - lat1) * fraction];
}

export function lerp(a: number, b: number, fraction: number): number {
  return a + (b - a) * fraction;
}

/** Point on a circle of `radiusM` around `center`, at `angleDeg` (0 = east, CCW). */
export function pointOnCircle(
  center: GeoPosition,
  radiusM: number,
  angleDeg: number,
): GeoPosition2D {
  const [lon, lat] = center;
  const angleRad = toRadians(angleDeg);
  const latRad = toRadians(lat);
  // Local equirectangular approximation — fine at the radii orbit missions use.
  const dLat = ((radiusM * Math.sin(angleRad)) / EARTH_RADIUS_M) * (180 / Math.PI);
  const dLon =
    ((radiusM * Math.cos(angleRad)) / (EARTH_RADIUS_M * Math.cos(latRad))) * (180 / Math.PI);
  return [lon + dLon, lat + dLat];
}

const CLOSED_LOOP_TEMPLATES = new Set(["racetrack", "perimeter_patrol"]);
const ORBIT_PREVIEW_POINTS = 64;

/** A map-preview LineString for a trajectory — not the live evaluated position. */
export function trajectoryPreviewGeoJSON(trajectory: Trajectory): GeoLineString {
  if (trajectory.template === "orbit") {
    const [center, radiusM] = orbitCenterAndRadius(trajectory);
    const coordinates: GeoPosition2D[] = [];
    for (let i = 0; i <= ORBIT_PREVIEW_POINTS; i++) {
      coordinates.push(pointOnCircle(center, radiusM, (360 * i) / ORBIT_PREVIEW_POINTS));
    }
    return { type: "LineString", coordinates };
  }

  const ordered = [...trajectory.waypoints].sort((a, b) => a.sequence_index - b.sequence_index);
  const coordinates = ordered.map((w) => w.position.coordinates);
  if (CLOSED_LOOP_TEMPLATES.has(trajectory.template) && coordinates.length > 0) {
    coordinates.push(coordinates[0]);
  }
  return { type: "LineString", coordinates };
}

const DEFAULT_ORBIT_RADIUS_M = 100;

/** Shared by the preview line and the evaluator so they stay consistent. */
export function orbitCenterAndRadius(trajectory: Trajectory): [GeoPosition, number] {
  const ordered = [...trajectory.waypoints].sort((a, b) => a.sequence_index - b.sequence_index);
  const center = ordered[0].position.coordinates;
  // Documented assumption: template_parameters.radius_m is not required by
  // the backend schema (dict[str, float]); default to 100m if absent.
  const radiusM = trajectory.template_parameters.radius_m ?? DEFAULT_ORBIT_RADIUS_M;
  return [center, radiusM];
}
