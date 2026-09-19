import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ZonePolygonEditor } from "./ZonePolygonEditor";
import type { GeoPolygon } from "../../domain/types";

function square(): GeoPolygon {
  return {
    type: "Polygon",
    coordinates: [
      [
        [13.0, 52.0],
        [13.1, 52.0],
        [13.1, 52.1],
        [13.0, 52.1],
        [13.0, 52.0],
      ],
    ],
  };
}

describe("ZonePolygonEditor", () => {
  it("shows one row per vertex, excluding the closing duplicate of the first point", () => {
    render(<ZonePolygonEditor polygon={square()} onChange={vi.fn()} />);

    // A square ring has 5 points (4 corners + the closing duplicate of the
    // first) — 4 editable vertex rows, no 5th row for the duplicate.
    expect(screen.getByTestId("zone-vertex-0")).toBeInTheDocument();
    expect(screen.getByTestId("zone-vertex-1")).toBeInTheDocument();
    expect(screen.getByTestId("zone-vertex-2")).toBeInTheDocument();
    expect(screen.getByTestId("zone-vertex-3")).toBeInTheDocument();
    expect(screen.queryByTestId("zone-vertex-4")).not.toBeInTheDocument();
  });

  it("adding a point keeps the ring closed", () => {
    const onChange = vi.fn();
    render(<ZonePolygonEditor polygon={square()} onChange={onChange} />);

    fireEvent.click(screen.getByText("+ Point"));

    const result = onChange.mock.calls[0][0] as GeoPolygon;
    const ring = result.coordinates[0];
    expect(ring).toHaveLength(6); // 4 authored vertices + 1 new + closing point
    expect(ring[0]).toEqual(ring[ring.length - 1]);
  });

  it("removing a vertex keeps the ring closed and re-derives the closing point", () => {
    const onChange = vi.fn();
    render(<ZonePolygonEditor polygon={square()} onChange={onChange} />);

    fireEvent.click(within(screen.getByTestId("zone-vertex-1")).getByText("Remove"));

    const result = onChange.mock.calls[0][0] as GeoPolygon;
    const ring = result.coordinates[0];
    expect(ring).toHaveLength(4); // 3 authored vertices + closing point
    expect(ring[0]).toEqual(ring[ring.length - 1]);
    expect(ring.slice(0, -1)).toEqual([
      [13.0, 52.0],
      [13.1, 52.1],
      [13.0, 52.1],
    ]);
  });

  it("cannot remove below a triangle (3 vertices)", () => {
    const triangle: GeoPolygon = {
      type: "Polygon",
      coordinates: [
        [
          [13.0, 52.0],
          [13.1, 52.0],
          [13.05, 52.1],
          [13.0, 52.0],
        ],
      ],
    };
    render(<ZonePolygonEditor polygon={triangle} onChange={vi.fn()} />);

    for (const button of screen.getAllByText("Remove")) {
      expect(button).toBeDisabled();
    }
  });

  it("editing a vertex's lon/lat updates that point only", () => {
    const onChange = vi.fn();
    render(<ZonePolygonEditor polygon={square()} onChange={onChange} />);

    const row0 = screen.getByTestId("zone-vertex-0");
    fireEvent.change(within(row0).getByLabelText("Lon"), { target: { value: "14.0" } });

    const result = onChange.mock.calls[0][0] as GeoPolygon;
    expect(result.coordinates[0][0]).toEqual([14.0, 52.0]);
    expect(result.coordinates[0][1]).toEqual([13.1, 52.0]);
  });

  it("reorders vertices with the move-up/down buttons", () => {
    const onChange = vi.fn();
    render(<ZonePolygonEditor polygon={square()} onChange={onChange} />);

    const row1 = screen.getByTestId("zone-vertex-1");
    fireEvent.click(within(row1).getByText("↓"));

    const result = onChange.mock.calls[0][0] as GeoPolygon;
    expect(result.coordinates[0].slice(0, -1)).toEqual([
      [13.0, 52.0],
      [13.1, 52.1],
      [13.1, 52.0],
      [13.0, 52.1],
    ]);
  });
});
