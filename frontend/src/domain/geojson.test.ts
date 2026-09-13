import { describe, expect, it } from "vitest";
import {
  bearingDegrees,
  haversineDistanceMeters,
  lerpPosition,
  orbitCenterAndRadius,
  pointOnCircle,
  trajectoryPreviewGeoJSON,
} from "./geojson";
import type { Trajectory, Waypoint } from "./types";

function waypoint(
  sequenceIndex: number,
  lon: number,
  lat: number,
  overrides: Partial<Waypoint> = {},
): Waypoint {
  return {
    sequence_index: sequenceIndex,
    position: { type: "Point", coordinates: [lon, lat] },
    altitude_m: 100,
    altitude_reference: "agl",
    speed_mps: null,
    heading_deg: null,
    hold_seconds: 0,
    ...overrides,
  };
}

describe("haversineDistanceMeters", () => {
  it("returns ~0 for identical points", () => {
    expect(haversineDistanceMeters([13.4, 52.5], [13.4, 52.5])).toBeCloseTo(0, 3);
  });

  it("matches a known great-circle distance (roughly 1 degree of latitude ~= 111.2km)", () => {
    const d = haversineDistanceMeters([13.4, 52.0], [13.4, 53.0]);
    expect(d).toBeGreaterThan(110_000);
    expect(d).toBeLessThan(112_000);
  });
});

describe("bearingDegrees", () => {
  it("is ~0 (north) for due-north movement", () => {
    expect(bearingDegrees([13.4, 52.0], [13.4, 52.1])).toBeCloseTo(0, 0);
  });

  it("is ~90 (east) for due-east movement", () => {
    expect(bearingDegrees([13.0, 52.0], [13.2, 52.0])).toBeCloseTo(90, 0);
  });
});

describe("lerpPosition", () => {
  it("interpolates linearly between two positions", () => {
    expect(lerpPosition([0, 0], [10, 20], 0.5)).toEqual([5, 10]);
  });

  it("returns the start position at fraction 0 and end at fraction 1", () => {
    expect(lerpPosition([1, 2], [3, 4], 0)).toEqual([1, 2]);
    expect(lerpPosition([1, 2], [3, 4], 1)).toEqual([3, 4]);
  });
});

describe("pointOnCircle", () => {
  it("stays approximately radiusM away from the center", () => {
    const center: [number, number] = [13.4, 52.5];
    const radiusM = 200;
    for (const angle of [0, 45, 90, 180, 270]) {
      const p = pointOnCircle(center, radiusM, angle);
      expect(haversineDistanceMeters(center, p)).toBeCloseTo(radiusM, -1);
    }
  });
});

describe("orbitCenterAndRadius", () => {
  it("uses waypoint[0] as center and defaults radius to 100m when absent", () => {
    const trajectory: Trajectory = {
      template: "orbit",
      waypoints: [waypoint(0, 13.4, 52.5), waypoint(1, 13.41, 52.5)],
      default_speed_mps: 10,
      template_parameters: {},
    };
    const [center, radius] = orbitCenterAndRadius(trajectory);
    expect(center).toEqual([13.4, 52.5]);
    expect(radius).toBe(100);
  });

  it("uses template_parameters.radius_m when present", () => {
    const trajectory: Trajectory = {
      template: "orbit",
      waypoints: [waypoint(0, 13.4, 52.5), waypoint(1, 13.41, 52.5)],
      default_speed_mps: 10,
      template_parameters: { radius_m: 250 },
    };
    expect(orbitCenterAndRadius(trajectory)[1]).toBe(250);
  });
});

describe("trajectoryPreviewGeoJSON", () => {
  it("returns waypoints in order for waypoint_transit", () => {
    const trajectory: Trajectory = {
      template: "waypoint_transit",
      waypoints: [waypoint(1, 1, 1), waypoint(0, 0, 0)],
      default_speed_mps: 10,
      template_parameters: {},
    };
    const geojson = trajectoryPreviewGeoJSON(trajectory);
    expect(geojson.coordinates).toEqual([
      [0, 0],
      [1, 1],
    ]);
  });

  it("closes the loop for racetrack/perimeter_patrol", () => {
    const trajectory: Trajectory = {
      template: "racetrack",
      waypoints: [waypoint(0, 0, 0), waypoint(1, 1, 0), waypoint(2, 1, 1)],
      default_speed_mps: 10,
      template_parameters: {},
    };
    const geojson = trajectoryPreviewGeoJSON(trajectory);
    expect(geojson.coordinates[0]).toEqual(geojson.coordinates[geojson.coordinates.length - 1]);
    expect(geojson.coordinates).toHaveLength(4);
  });

  it("returns a closed circle approximation for orbit", () => {
    const trajectory: Trajectory = {
      template: "orbit",
      waypoints: [waypoint(0, 13.4, 52.5), waypoint(1, 13.41, 52.5)],
      default_speed_mps: 10,
      template_parameters: { radius_m: 100 },
    };
    const geojson = trajectoryPreviewGeoJSON(trajectory);
    expect(geojson.coordinates[0]).toEqual(geojson.coordinates[geojson.coordinates.length - 1]);
    expect(geojson.coordinates.length).toBeGreaterThan(10);
  });
});
