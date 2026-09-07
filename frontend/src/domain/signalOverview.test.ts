import { describe, expect, it } from "vitest";
import { flattenLinks } from "./signalOverview";
import type { DroneMission, DroneRfLink, Platform, Trajectory } from "./types";

const PLATFORM: Platform = {
  name: "test-quad",
  category: "multirotor",
  max_speed_mps: 20,
  max_climb_rate_mps: null,
  notes: null,
};

const TRAJECTORY: Trajectory = {
  template: "waypoint_transit",
  waypoints: [
    {
      sequence_index: 0,
      position: { type: "Point", coordinates: [13.4, 52.5] },
      altitude_m: 100,
      altitude_reference: "agl",
      speed_mps: null,
      heading_deg: null,
      hold_seconds: 0,
    },
  ],
  default_speed_mps: 10,
  template_parameters: {},
};

function link(id: string, role: DroneRfLink["role"]): DroneRfLink {
  return {
    id,
    role,
    band: { freq_min_hz: 2_400_000_000, freq_max_hz: 2_483_500_000, allowed_channels_hz: [] },
    frequency_behaviour: {
      mode: "scripted",
      scripted_changes: [],
      mission_trigger_anchor: null,
      random_seed: null,
      mean_dwell_s: null,
      external_trigger_reference: null,
    },
    emissions: [],
    resource_preference: null,
  };
}

function mission(id: string, name: string, links: DroneRfLink[]): DroneMission {
  return {
    id,
    name,
    platform: PLATFORM,
    trajectory: TRAJECTORY,
    start_policy: "at_scenario_start",
    start_time_offset: null,
    rf_links: links,
  };
}

describe("flattenLinks", () => {
  it("returns one row per link across all missions, tagged with the owning mission", () => {
    const missions = [
      mission("m1", "Perimeter Patrol Alpha", [link("l1", "c2"), link("l2", "video")]),
      mission("m2", "Grid Search Bravo", [link("l3", "telemetry")]),
    ];
    const rows = flattenLinks(missions, 0);
    expect(rows).toHaveLength(3);
    expect(rows.map((r) => r.linkId)).toEqual(["l1", "l2", "l3"]);
    expect(rows[0].missionName).toBe("Perimeter Patrol Alpha");
    expect(rows[2].missionName).toBe("Grid Search Bravo");
  });

  it("returns an empty array when no missions have links", () => {
    expect(flattenLinks([mission("m1", "No Links", [])], 0)).toEqual([]);
  });

  it("carries the link's current frequency at the given scenario time", () => {
    const l = link("l1", "c2");
    l.frequency_behaviour.scripted_changes = [
      { at_offset: "PT10S", frequency_hz: 2_437_000_000, transition_type: "channel_switch" },
    ];
    const rows = flattenLinks([mission("m1", "M1", [l])], 20);
    expect(rows[0].currentFrequencyHz).toBe(2_437_000_000);
  });
});
