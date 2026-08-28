import { describe, expect, it } from "vitest";
import {
  arrivalSecondsAtWaypoint,
  evaluateMissionStartSeconds,
  evaluateMissionState,
  evaluateScenarioState,
  evaluateTimelineEventFireSeconds,
  scenarioDurationSeconds,
} from "./missionEvaluator";
import type {
  DroneMission,
  MissionRelativeTimelineEvent,
  Platform,
  Trajectory,
  Waypoint,
} from "./types";

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

// A straight 1000m-ish leg due north, easy to reason about.
const STRAIGHT_LEG: Trajectory = {
  template: "waypoint_transit",
  waypoints: [waypoint(0, 13.4, 52.5), waypoint(1, 13.4, 52.509)], // ~1000m north
  default_speed_mps: 10,
  template_parameters: {},
};

describe("evaluateMissionStartSeconds", () => {
  it("is 0 for at_scenario_start", () => {
    expect(evaluateMissionStartSeconds(mission(STRAIGHT_LEG))).toBe(0);
  });

  it("parses start_time_offset for at_time_offset", () => {
    const m = mission(STRAIGHT_LEG, { start_policy: "at_time_offset", start_time_offset: "PT30S" });
    expect(evaluateMissionStartSeconds(m)).toBe(30);
  });

  it("is Infinity for on_event/manual (never auto-starts in this milestone)", () => {
    expect(evaluateMissionStartSeconds(mission(STRAIGHT_LEG, { start_policy: "on_event" }))).toBe(
      Infinity,
    );
    expect(evaluateMissionStartSeconds(mission(STRAIGHT_LEG, { start_policy: "manual" }))).toBe(
      Infinity,
    );
  });
});

describe("evaluateMissionState — waypoint_transit", () => {
  const m = mission(STRAIGHT_LEG);

  it("is at the first waypoint, phase en_route, at t=0", () => {
    const state = evaluateMissionState(m, 0);
    expect(state.positionLonLat).toEqual([13.4, 52.5]);
    expect(state.phase).toBe("en_route");
    expect(state.speedMps).toBe(10);
  });

  it("is roughly halfway along the leg at half the transit time", () => {
    const totalDuration = scenarioDurationSeconds([m]);
    const state = evaluateMissionState(m, totalDuration / 2);
    expect(state.positionLonLat[1]).toBeCloseTo(52.5045, 3);
    expect(state.phase).toBe("en_route");
    expect(state.completionFraction).toBeCloseTo(0.5, 5);
  });

  it("reports phase completed and clamps position at/after the end", () => {
    const totalDuration = scenarioDurationSeconds([m]);
    const atEnd = evaluateMissionState(m, totalDuration);
    const pastEnd = evaluateMissionState(m, totalDuration + 1000);
    expect(atEnd.phase).toBe("completed");
    expect(pastEnd.phase).toBe("completed");
    expect(pastEnd.positionLonLat).toEqual(atEnd.positionLonLat);
    expect(pastEnd.speedMps).toBe(0);
  });

  it("reports before_start before the mission's start time", () => {
    const m2 = mission(STRAIGHT_LEG, {
      start_policy: "at_time_offset",
      start_time_offset: "PT100S",
    });
    const state = evaluateMissionState(m2, 50);
    expect(state.phase).toBe("before_start");
    expect(state.positionLonLat).toEqual([13.4, 52.5]);
  });
});

describe("evaluateMissionState — hold_seconds", () => {
  it("pauses at a waypoint for hold_seconds before continuing", () => {
    const trajectory: Trajectory = {
      template: "waypoint_transit",
      waypoints: [waypoint(0, 13.4, 52.5, { hold_seconds: 20 }), waypoint(1, 13.41, 52.5)],
      default_speed_mps: 10,
      template_parameters: {},
    };
    const m = mission(trajectory);

    const duringHold = evaluateMissionState(m, 10);
    expect(duringHold.phase).toBe("holding");
    expect(duringHold.positionLonLat).toEqual([13.4, 52.5]);
    expect(duringHold.speedMps).toBe(0);

    const afterHold = evaluateMissionState(m, 21);
    expect(afterHold.phase).toBe("en_route");
  });

  it("loiter_then_depart: the final waypoint's hold_seconds delays completion", () => {
    const trajectory: Trajectory = {
      template: "loiter_then_depart",
      waypoints: [waypoint(0, 13.4, 52.5), waypoint(1, 13.41, 52.5, { hold_seconds: 15 })],
      default_speed_mps: 10,
      template_parameters: {},
    };
    const m = mission(trajectory);
    const transitOnlyDuration = scenarioDurationSeconds([m]) - 15;

    const rightAfterArrival = evaluateMissionState(m, transitOnlyDuration + 5);
    expect(rightAfterArrival.phase).toBe("holding");

    const afterLoiter = evaluateMissionState(m, transitOnlyDuration + 16);
    expect(afterLoiter.phase).toBe("completed");
  });
});

describe("evaluateMissionState — orbit", () => {
  const trajectory: Trajectory = {
    template: "orbit",
    waypoints: [waypoint(0, 13.4, 52.5), waypoint(1, 13.41, 52.5)],
    default_speed_mps: 10,
    template_parameters: { radius_m: 100 },
  };
  const m = mission(trajectory);

  it("stays approximately radius_m from the center at all times", () => {
    for (const t of [0, 5, 15, 40, 100]) {
      const state = evaluateMissionState(m, t);
      const dLon = state.positionLonLat[0] - 13.4;
      const dLat = state.positionLonLat[1] - 52.5;
      const approxMetersPerDegLat = 111_320;
      const distM = Math.sqrt(
        (dLon * approxMetersPerDegLat * Math.cos((52.5 * Math.PI) / 180)) ** 2 +
          (dLat * approxMetersPerDegLat) ** 2,
      );
      expect(distM).toBeCloseTo(100, -1);
    }
  });

  it("wraps completionFraction around after one period", () => {
    const period = (2 * Math.PI * 100) / 10; // circumference / speed
    const justAfterStart = evaluateMissionState(m, 1);
    const oneFullPeriodLater = evaluateMissionState(m, 1 + period);
    expect(oneFullPeriodLater.positionLonLat[0]).toBeCloseTo(justAfterStart.positionLonLat[0], 6);
    expect(oneFullPeriodLater.positionLonLat[1]).toBeCloseTo(justAfterStart.positionLonLat[1], 6);
  });

  it("never reports phase completed (loops indefinitely)", () => {
    expect(evaluateMissionState(m, 10_000).phase).toBe("en_route");
  });
});

describe("evaluateMissionState — racetrack/perimeter_patrol looping", () => {
  it("loops back to waypoint 0 after the last waypoint, indefinitely", () => {
    const trajectory: Trajectory = {
      template: "racetrack",
      waypoints: [waypoint(0, 13.4, 52.5), waypoint(1, 13.41, 52.5), waypoint(2, 13.41, 52.51)],
      default_speed_mps: 10,
      template_parameters: {},
    };
    const m = mission(trajectory);
    const lapDuration = scenarioDurationSeconds([m]);

    const startOfLap1 = evaluateMissionState(m, 0.001);
    const startOfLap2 = evaluateMissionState(m, lapDuration + 0.001);
    expect(startOfLap2.positionLonLat[0]).toBeCloseTo(startOfLap1.positionLonLat[0], 5);
    expect(startOfLap2.positionLonLat[1]).toBeCloseTo(startOfLap1.positionLonLat[1], 5);
    expect(startOfLap2.phase).not.toBe("completed");
  });
});

describe("determinism", () => {
  it("produces identical output for identical inputs, regardless of call order/count", () => {
    const m = mission(STRAIGHT_LEG);
    const t = 37;

    const first = evaluateMissionState(m, t);
    // Call the evaluator many times with different inputs in between to
    // rule out any hidden shared/module-level mutable state.
    evaluateMissionState(m, 0);
    evaluateMissionState(mission(STRAIGHT_LEG, { id: "other" }), 999);
    const second = evaluateMissionState(m, t);

    expect(second).toEqual(first);
  });

  it("evaluateScenarioState is a pure map over evaluateMissionState", () => {
    const m1 = mission(STRAIGHT_LEG, { id: "a" });
    const m2 = mission(STRAIGHT_LEG, { id: "b" });
    const result = evaluateScenarioState([m1, m2], 5);

    expect(result.get("a")).toEqual(evaluateMissionState(m1, 5));
    expect(result.get("b")).toEqual(evaluateMissionState(m2, 5));
  });
});

describe("arrivalSecondsAtWaypoint", () => {
  it("returns the mission start time for waypoint 0", () => {
    const m = mission(STRAIGHT_LEG, { start_policy: "at_time_offset", start_time_offset: "PT10S" });
    expect(arrivalSecondsAtWaypoint(m, 0)).toBe(10);
  });

  it("returns the transit-completion time for a later waypoint", () => {
    const m = mission(STRAIGHT_LEG);
    const expected = scenarioDurationSeconds([m]);
    expect(arrivalSecondsAtWaypoint(m, 1)).toBeCloseTo(expected, 5);
  });

  it("returns null for orbit (not well-defined for continuous motion)", () => {
    const trajectory: Trajectory = {
      template: "orbit",
      waypoints: [waypoint(0, 13.4, 52.5), waypoint(1, 13.41, 52.5)],
      default_speed_mps: 10,
      template_parameters: {},
    };
    expect(arrivalSecondsAtWaypoint(mission(trajectory), 1)).toBeNull();
  });
});

describe("evaluateTimelineEventFireSeconds", () => {
  it("resolves absolute events directly from their duration", () => {
    const event = {
      id: "e1",
      kind: "absolute" as const,
      label: null,
      notes: null,
      scenario_time_offset: "PT15S",
    };
    expect(evaluateTimelineEventFireSeconds(event, [])).toBe(15);
  });

  it("resolves mission_relative(mission_start) against the mission's own start", () => {
    const m = mission(STRAIGHT_LEG, {
      id: "m1",
      start_policy: "at_time_offset",
      start_time_offset: "PT10S",
    });
    const event: MissionRelativeTimelineEvent = {
      id: "e1",
      kind: "mission_relative",
      label: null,
      notes: null,
      mission_id: "m1",
      anchor: "mission_start",
      waypoint_sequence_index: null,
      offset: "PT5S",
    };
    expect(evaluateTimelineEventFireSeconds(event, [m])).toBe(15);
  });

  it("resolves mission_relative(waypoint) against that waypoint's arrival time", () => {
    const m = mission(STRAIGHT_LEG);
    const event: MissionRelativeTimelineEvent = {
      id: "e1",
      kind: "mission_relative",
      label: null,
      notes: null,
      mission_id: "m1",
      anchor: "waypoint",
      waypoint_sequence_index: 1,
      offset: "PT0S",
    };
    expect(evaluateTimelineEventFireSeconds(event, [m])).toBeCloseTo(
      scenarioDurationSeconds([m]),
      5,
    );
  });

  it("returns null for area_entry/phase_completion anchors and non-absolute/mission_relative kinds", () => {
    const m = mission(STRAIGHT_LEG);
    const areaEntryEvent: MissionRelativeTimelineEvent = {
      id: "e1",
      kind: "mission_relative",
      label: null,
      notes: null,
      mission_id: "m1",
      anchor: "area_entry",
      waypoint_sequence_index: null,
      offset: "PT0S",
    };
    expect(evaluateTimelineEventFireSeconds(areaEntryEvent, [m])).toBeNull();

    expect(
      evaluateTimelineEventFireSeconds(
        { id: "e2", kind: "manual_gated", label: null, notes: null, gate_description: "go" },
        [m],
      ),
    ).toBeNull();
  });

  it("returns null when the referenced mission doesn't exist", () => {
    const event: MissionRelativeTimelineEvent = {
      id: "e1",
      kind: "mission_relative",
      label: null,
      notes: null,
      mission_id: "does-not-exist",
      anchor: "mission_start",
      waypoint_sequence_index: null,
      offset: "PT0S",
    };
    expect(evaluateTimelineEventFireSeconds(event, [])).toBeNull();
  });
});
