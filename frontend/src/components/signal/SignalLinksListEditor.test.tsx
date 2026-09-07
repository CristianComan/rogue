import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { SignalLinksListEditor } from "./SignalLinksListEditor";
import type { DroneMission, DroneRfLink, Platform, Trajectory } from "../../domain/types";

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

describe("SignalLinksListEditor", () => {
  it("shows an empty-state message when there are no RF links", () => {
    render(
      <SignalLinksListEditor
        missions={[mission("m1", "M1", [])]}
        scenarioTimeSeconds={0}
        selection={null}
        onSelect={vi.fn()}
      />,
    );
    expect(screen.getByText(/no rf links/i)).toBeInTheDocument();
  });

  it("renders one row per link, labeled with its owning mission", () => {
    render(
      <SignalLinksListEditor
        missions={[mission("m1", "Perimeter Patrol Alpha", [link("l1", "c2")])]}
        scenarioTimeSeconds={0}
        selection={null}
        onSelect={vi.fn()}
      />,
    );
    expect(screen.getByText("Perimeter Patrol Alpha")).toBeInTheDocument();
    expect(screen.getByTestId("signal-links-row-l1")).toBeInTheDocument();
  });

  it("calls onSelect with the rfLink selection when a row is clicked", () => {
    const onSelect = vi.fn();
    render(
      <SignalLinksListEditor
        missions={[mission("m1", "M1", [link("l1", "c2")])]}
        scenarioTimeSeconds={0}
        selection={null}
        onSelect={onSelect}
      />,
    );
    fireEvent.click(screen.getByTestId("signal-links-row-l1"));
    expect(onSelect).toHaveBeenCalledWith({ kind: "rfLink", missionId: "m1", linkId: "l1" });
  });
});
