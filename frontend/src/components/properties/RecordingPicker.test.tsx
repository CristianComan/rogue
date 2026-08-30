import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { RecordingPicker } from "./RecordingPicker";
import type { IQRecording } from "../../domain/types";

function recording(overrides: Partial<IQRecording> = {}): IQRecording {
  return {
    id: "11111111-1111-4111-8111-111111111111",
    version: 1,
    metadata_object_key: "k.sigmf-meta",
    data_object_key: "k.sigmf-data",
    sha256_metadata: "a".repeat(64),
    sha256_data: "a".repeat(64),
    sample_format: "cf32_le",
    sample_rate_hz: 1_000_000,
    sample_count: 1_000_000,
    duration_s: 1,
    center_frequency_hz: 2_450_000_000,
    provenance: null,
    access_classification: "restricted",
    allowed_use_constraints: [],
    allowed_frequency_min_hz: null,
    allowed_frequency_max_hz: null,
    extra_sigmf_fields: {},
    ...overrides,
  };
}

describe("RecordingPicker", () => {
  it("renders one option per catalogue entry, labeled from provenance's platform= token", () => {
    const recordings = [
      recording({ id: "r1", provenance: "campaign=x, drone_id=00, platform=DJI Mavic 2 Pro" }),
      recording({ id: "r2", provenance: "campaign=x, drone_id=01, platform=Parrot ANAFI" }),
    ];
    render(<RecordingPicker recordings={recordings} value="" onChange={vi.fn()} />);

    expect(screen.getByText(/DJI Mavic 2 Pro/)).toBeInTheDocument();
    expect(screen.getByText(/Parrot ANAFI/)).toBeInTheDocument();
  });

  it("groups platform-matching entries into a 'Matching platform' optgroup, ahead of the rest", () => {
    const recordings = [
      recording({ id: "r1", provenance: "platform=DJI Mavic 2 Pro" }),
      recording({ id: "r2", provenance: "platform=Parrot ANAFI" }),
    ];
    render(
      <RecordingPicker
        recordings={recordings}
        value=""
        onChange={vi.fn()}
        preferredPlatform="DJI Mavic 2 Pro"
      />,
    );

    const matchingGroup = screen.getByRole("group", { name: /Matching platform/ });
    expect(within(matchingGroup).getByText(/DJI Mavic 2 Pro/)).toBeInTheDocument();
    expect(within(matchingGroup).queryByText(/Parrot ANAFI/)).not.toBeInTheDocument();

    const allGroup = screen.getByRole("group", { name: "All recordings" });
    expect(within(allGroup).getByText(/Parrot ANAFI/)).toBeInTheDocument();
  });

  it("does not hard-filter — an unmatched platform still leaves every recording pickable", () => {
    const recordings = [recording({ id: "r1", provenance: "platform=Parrot ANAFI" })];
    render(
      <RecordingPicker
        recordings={recordings}
        value=""
        onChange={vi.fn()}
        preferredPlatform="DJI Mavic 2 Pro"
      />,
    );

    expect(screen.queryByRole("group", { name: /Matching platform/ })).not.toBeInTheDocument();
    expect(screen.getByText(/Parrot ANAFI/)).toBeInTheDocument();
  });

  it("selecting an option calls onChange with that recording's id", () => {
    const recordings = [recording({ id: "r1", provenance: "platform=DJI Mavic 2 Pro" })];
    const onChange = vi.fn();
    render(<RecordingPicker recordings={recordings} value="" onChange={onChange} />);

    fireEvent.change(screen.getByLabelText("Recording"), { target: { value: "r1" } });

    expect(onChange).toHaveBeenCalledWith("r1");
  });

  it("a value not in the catalogue falls back to a plain text input instead of hiding it", () => {
    const recordings = [recording({ id: "r1" })];
    render(<RecordingPicker recordings={recordings} value="legacy-id" onChange={vi.fn()} />);

    expect(screen.getByPlaceholderText("recording UUID")).toHaveValue("legacy-id");
  });
});
