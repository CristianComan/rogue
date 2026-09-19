import { describe, expect, it } from "vitest";
import { rangeAndRangeRate, sampleRangeSeries } from "./doppler";
import type { DroneMission, Platform, Receiver, Trajectory, Waypoint } from "./types";

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

const PLATFORM: Platform = {
  name: "test-quad",
  category: "multirotor",
  max_speed_mps: 20,
  max_climb_rate_mps: null,
  notes: null,
};

function mission(trajectory: Trajectory, overrides: Partial<DroneMission> = {}): DroneMission {
  return {
    id: "m1",
    name: "test-mission",
    platform: PLATFORM,
    trajectory,
    start_policy: "at_scenario_start",
    start_time_offset: null,
    rf_links: [],
    ...overrides,
  };
}

function receiver(lon: number, lat: number, overrides: Partial<Receiver> = {}): Receiver {
  return {
    id: "rx1",
    name: "test-receiver",
    receiver_type: "monitor",
    position: { type: "Point", coordinates: [lon, lat] },
    array_group_id: null,
    element_index: null,
    element_local_offset_m: null,
    ...overrides,
  };
}

// Straight leg heading due north from the receiver's longitude, ~1000m long,
// at constant 10 m/s (default_speed_mps) — a drone flying directly away from
// a receiver planted at the start waypoint should show a steadily positive
// (receding) range-rate close to its ground speed.
const RECEDING_LEG: Trajectory = {
  template: "waypoint_transit",
  waypoints: [waypoint(0, 13.4, 52.5), waypoint(1, 13.4, 52.509)],
  default_speed_mps: 10,
  template_parameters: {},
};

describe("rangeAndRangeRate", () => {
  it("reports zero range at the drone's own position", () => {
    const rx = receiver(13.4, 52.5);
    const m = mission(RECEDING_LEG);
    const { rangeM } = rangeAndRangeRate(rx, m, 0);
    expect(rangeM).toBeCloseTo(0, 0);
  });

  it("reports a positive (receding) range-rate close to ground speed when flying directly away", () => {
    const rx = receiver(13.4, 52.5);
    const m = mission(RECEDING_LEG);
    const { rangeRateMps } = rangeAndRangeRate(rx, m, 20);
    expect(rangeRateMps).toBeGreaterThan(0);
    expect(rangeRateMps).toBeCloseTo(10, 0);
  });

  it("reports range increasing over time while receding", () => {
    const rx = receiver(13.4, 52.5);
    const m = mission(RECEDING_LEG);
    const early = rangeAndRangeRate(rx, m, 10).rangeM;
    const later = rangeAndRangeRate(rx, m, 50).rangeM;
    expect(later).toBeGreaterThan(early);
  });
});

describe("sampleRangeSeries", () => {
  it("returns sampleCount evenly-spaced samples spanning [0, durationSeconds]", () => {
    const rx = receiver(13.4, 52.5);
    const m = mission(RECEDING_LEG);
    const samples = sampleRangeSeries(rx, m, 100, 5);
    expect(samples).toHaveLength(5);
    expect(samples[0].scenarioTimeSeconds).toBe(0);
    expect(samples[4].scenarioTimeSeconds).toBe(100);
  });

  it("falls back to a single sample at t=0 for a zero-duration scenario", () => {
    const rx = receiver(13.4, 52.5);
    const m = mission(RECEDING_LEG);
    const samples = sampleRangeSeries(rx, m, 0);
    expect(samples).toHaveLength(1);
    expect(samples[0].scenarioTimeSeconds).toBe(0);
  });
});
