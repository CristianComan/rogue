import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { SignalTimeline } from "./SignalTimeline";
import { ScenarioTimeProvider } from "../../state/scenarioTimeContext";
import type { DroneMission } from "../../domain/types";

function mission(overrides: Partial<DroneMission> = {}): DroneMission {
  return {
    id: "m1",
    name: "Perimeter Patrol Alpha",
    platform: {
      name: "sim",
      category: "multirotor",
      max_speed_mps: 15,
      max_climb_rate_mps: null,
      notes: null,
    },
    trajectory: {
      template: "waypoint_transit",
      waypoints: [],
      default_speed_mps: 10,
      template_parameters: {},
    },
    start_policy: "at_scenario_start",
    start_time_offset: null,
    rf_links: [
      {
        id: "link-1",
        role: "c2",
        band: { freq_min_hz: 2_400_000_000, freq_max_hz: 2_483_500_000, allowed_channels_hz: [] },
        frequency_behaviour: {
          mode: "scripted",
          scripted_changes: [],
          mission_trigger_anchor: null,
          random_seed: null,
          mean_dwell_s: null,
          external_trigger_reference: null,
        },
        emissions: [
          {
            id: "e1",
            recording: { recording_id: "rec-1", version: 1, note: null },
            start_offset: "PT0S",
            duration_override: "PT10S",
            gain_offset_db: -6,
            loop: false,
            notes: null,
          },
        ],
        resource_preference: null,
      },
    ],
    ...overrides,
  };
}

function renderTimeline(missions: DroneMission[], onSelect = vi.fn()) {
  render(
    <ScenarioTimeProvider maxSeconds={100}>
      <SignalTimeline
        missions={missions}
        maxSeconds={100}
        catalogue={[]}
        selection={null}
        onSelect={onSelect}
      />
    </ScenarioTimeProvider>,
  );
  return onSelect;
}

describe("SignalTimeline", () => {
  it("shows an empty state when there are no RF links", () => {
    renderTimeline([mission({ rf_links: [] })]);
    expect(screen.getByText(/no rf links/i)).toBeInTheDocument();
  });

  it("renders one row per RF link with its role and mission", () => {
    renderTimeline([mission()]);
    expect(screen.getByTestId("signal-timeline-row-link-1")).toBeInTheDocument();
    expect(screen.getByText("c2")).toBeInTheDocument();
    expect(screen.getByText("Perimeter Patrol Alpha")).toBeInTheDocument();
  });

  it("selects the rfLink on row click", () => {
    const onSelect = renderTimeline([mission()]);
    fireEvent.click(screen.getByTestId("signal-timeline-row-link-1"));
    expect(onSelect).toHaveBeenCalledWith({ kind: "rfLink", missionId: "m1", linkId: "link-1" });
  });
});
