import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { DopplerBlade } from "./DopplerBlade";
import type { DroneMission, Platform, Receiver, Trajectory, Waypoint } from "../../domain/types";

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

const RECEDING_LEG: Trajectory = {
  template: "waypoint_transit",
  waypoints: [waypoint(0, 13.4, 52.5), waypoint(1, 13.4, 52.509)],
  default_speed_mps: 10,
  template_parameters: {},
};

function mission(overrides: Partial<DroneMission> = {}): DroneMission {
  return {
    id: "m1",
    name: "Perimeter Patrol Alpha",
    platform: PLATFORM,
    trajectory: RECEDING_LEG,
    start_policy: "at_scenario_start",
    start_time_offset: null,
    rf_links: [],
    ...overrides,
  };
}

function receiver(overrides: Partial<Receiver> = {}): Receiver {
  return {
    id: "rx1",
    name: "North Mast",
    receiver_type: "monitor",
    position: { type: "Point", coordinates: [13.4, 52.5] },
    array_group_id: null,
    element_index: null,
    element_local_offset_m: null,
    ...overrides,
  };
}

describe("DopplerBlade", () => {
  it("shows an empty-state message when there are no receivers or missions", () => {
    render(
      <DopplerBlade
        receivers={[]}
        missions={[]}
        scenarioTimeSeconds={0}
        maxSeconds={100}
        onClose={vi.fn()}
      />,
    );
    expect(screen.getByText(/add at least one receiver and one mission/i)).toBeInTheDocument();
  });

  it("renders one card and matrix row per receiver/mission pair", () => {
    render(
      <DopplerBlade
        receivers={[receiver()]}
        missions={[mission()]}
        scenarioTimeSeconds={20}
        maxSeconds={100}
        onClose={vi.fn()}
      />,
    );
    expect(screen.getAllByText(/North Mast · Perimeter Patrol Alpha/)).toHaveLength(1);
    expect(screen.getAllByText(/North Mast ▸ Perimeter Patrol Alpha/)).toHaveLength(1);
  });

  it("follows the main clock while linked", () => {
    render(
      <DopplerBlade
        receivers={[receiver()]}
        missions={[mission()]}
        scenarioTimeSeconds={65}
        maxSeconds={600}
        onClose={vi.fn()}
      />,
    );
    expect(screen.getByText("01:05")).toBeInTheDocument();
    expect(screen.getByText("Linked")).toBeInTheDocument();
  });

  it("switches to an independent scrub when unlinked", () => {
    render(
      <DopplerBlade
        receivers={[receiver()]}
        missions={[mission()]}
        scenarioTimeSeconds={65}
        maxSeconds={600}
        onClose={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByText("Linked"));
    expect(screen.getByText("Unlinked")).toBeInTheDocument();
    const slider = screen.getByRole("slider");
    expect(slider).not.toBeDisabled();
    fireEvent.change(slider, { target: { value: "200" } });
    expect(screen.getByText("03:20")).toBeInTheDocument();
  });

  it("calls onClose from the blade's close button", () => {
    const onClose = vi.fn();
    render(
      <DopplerBlade
        receivers={[receiver()]}
        missions={[mission()]}
        scenarioTimeSeconds={0}
        maxSeconds={100}
        onClose={onClose}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /close/i }));
    expect(onClose).toHaveBeenCalled();
  });
});
