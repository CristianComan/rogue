import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { WaypointListEditor } from "./WaypointListEditor";
import type { Waypoint } from "../../domain/types";

function waypoint(sequenceIndex: number, lon: number, lat: number): Waypoint {
  return {
    sequence_index: sequenceIndex,
    position: { type: "Point", coordinates: [lon, lat] },
    altitude_m: 100,
    altitude_reference: "agl",
    speed_mps: null,
    heading_deg: null,
    hold_seconds: 0,
  };
}

describe("WaypointListEditor", () => {
  it("renders one row per waypoint, ordered by sequence_index", () => {
    render(
      <WaypointListEditor waypoints={[waypoint(1, 1, 1), waypoint(0, 0, 0)]} onChange={vi.fn()} />,
    );

    expect(screen.getByTestId("waypoint-row-0")).toHaveTextContent("Waypoint 0");
    expect(screen.getByTestId("waypoint-row-1")).toHaveTextContent("Waypoint 1");
  });

  it("adds a waypoint, copying the last one's altitude", () => {
    const onChange = vi.fn();
    render(
      <WaypointListEditor waypoints={[waypoint(0, 0, 0), waypoint(1, 1, 1)]} onChange={onChange} />,
    );

    fireEvent.click(screen.getByText("+ Waypoint"));

    expect(onChange).toHaveBeenCalledWith([
      expect.objectContaining({ sequence_index: 0 }),
      expect.objectContaining({ sequence_index: 1 }),
      expect.objectContaining({ sequence_index: 2, altitude_m: 100 }),
    ]);
  });

  it("removes a waypoint and renumbers the rest", () => {
    const onChange = vi.fn();
    render(
      <WaypointListEditor
        waypoints={[waypoint(0, 0, 0), waypoint(1, 1, 1), waypoint(2, 2, 2)]}
        onChange={onChange}
      />,
    );

    fireEvent.click(screen.getAllByText("Remove")[1]);

    const result = onChange.mock.calls[0][0] as Waypoint[];
    expect(result.map((w) => w.sequence_index)).toEqual([0, 1]);
    expect(result.map((w) => w.position.coordinates[0])).toEqual([0, 2]);
  });

  it("cannot remove below two waypoints", () => {
    render(
      <WaypointListEditor waypoints={[waypoint(0, 0, 0), waypoint(1, 1, 1)]} onChange={vi.fn()} />,
    );

    const removeButtons = screen.getAllByText("Remove");
    expect(removeButtons[0]).toBeDisabled();
    expect(removeButtons[1]).toBeDisabled();
  });

  it("reorders waypoints with the move-up/down buttons", () => {
    const onChange = vi.fn();
    render(
      <WaypointListEditor
        waypoints={[waypoint(0, 0, 0), waypoint(1, 1, 1), waypoint(2, 2, 2)]}
        onChange={onChange}
      />,
    );

    const row1 = screen.getByTestId("waypoint-row-1");
    fireEvent.click(within(row1).getByText("↓"));

    const result = onChange.mock.calls[0][0] as Waypoint[];
    // Row 1 (originally at lon=1) moved down, swapping with row 2 (lon=2).
    expect(result.map((w) => w.position.coordinates[0])).toEqual([0, 2, 1]);
  });
});
