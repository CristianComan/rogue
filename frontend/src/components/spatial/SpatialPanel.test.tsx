import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { SpatialPanel } from "./SpatialPanel";
import type { ScenarioContent } from "../../domain/types";

function content(overrides: Partial<ScenarioContent> = {}): ScenarioContent {
  return {
    zones: [],
    missions: [],
    receivers: [],
    timeline_events: [],
    ...overrides,
  };
}

describe("SpatialPanel", () => {
  it("renders the Spatial Knowledge heading and object lists", () => {
    render(
      <SpatialPanel
        content={content()}
        scenarioTimeSeconds={0}
        maxSeconds={100}
        selection={null}
        onSelect={vi.fn()}
      />,
    );
    expect(screen.getByText("Spatial Knowledge")).toBeInTheDocument();
  });

  it("opens the Doppler blade from its button and closes it again", () => {
    render(
      <SpatialPanel
        content={content()}
        scenarioTimeSeconds={0}
        maxSeconds={100}
        selection={null}
        onSelect={vi.fn()}
      />,
    );
    expect(screen.queryByText(/receiver geometry & doppler overview/i)).not.toBeInTheDocument();
    fireEvent.click(screen.getByText("Doppler ▸"));
    expect(screen.getByText(/receiver geometry & doppler overview/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /close/i }));
    expect(screen.queryByText(/receiver geometry & doppler overview/i)).not.toBeInTheDocument();
  });
});
