import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { RfLinkForm } from "./RfLinkForm";
import type { DroneRfLink } from "../../domain/types";

function link(overrides: Partial<DroneRfLink> = {}): DroneRfLink {
  return {
    id: "l1",
    role: "c2",
    band: { freq_min_hz: 2_400_000_000, freq_max_hz: 2_483_500_000, allowed_channels_hz: [] },
    frequency_behaviour: {
      mode: "scripted",
      scripted_changes: [
        { at_offset: "PT0S", frequency_hz: 2_412_000_000, transition_type: "channel_switch" },
      ],
      mission_trigger_anchor: null,
      random_seed: null,
      mean_dwell_s: null,
      external_trigger_reference: null,
    },
    emissions: [],
    resource_preference: null,
    ...overrides,
  };
}

/** catalogue/platformName aren't exercised by most of these tests — RecordingPicker.test.tsx covers them. */
const catalogueProps = { catalogue: [], platformName: "Generic Quad" };

describe("RfLinkForm", () => {
  it("shows the scripted-changes editor when mode is scripted", () => {
    render(<RfLinkForm link={link()} onChange={vi.fn()} onDelete={vi.fn()} {...catalogueProps} />);

    expect(screen.getByTestId("scripted-change-0")).toBeInTheDocument();
    expect(screen.getByText("+ Scripted change")).toBeInTheDocument();
  });

  it("hides the scripted-changes editor for non-scripted modes", () => {
    render(
      <RfLinkForm
        link={link({
          frequency_behaviour: {
            mode: "probabilistic_adaptive",
            scripted_changes: [],
            mission_trigger_anchor: null,
            random_seed: 42,
            mean_dwell_s: 5,
            external_trigger_reference: null,
          },
        })}
        onChange={vi.fn()}
        onDelete={vi.fn()}
        {...catalogueProps}
      />,
    );

    expect(screen.queryByText("+ Scripted change")).not.toBeInTheDocument();
  });

  it("switching mode via the select calls onChange with the new mode", () => {
    const onChange = vi.fn();
    render(<RfLinkForm link={link()} onChange={onChange} onDelete={vi.fn()} {...catalogueProps} />);

    fireEvent.change(screen.getByLabelText("Mode"), { target: { value: "mission_triggered" } });

    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({
        frequency_behaviour: expect.objectContaining({ mode: "mission_triggered" }),
      }),
    );
  });

  it("adds an emission with an empty recording pointer, PT0S start offset and no duration override", () => {
    const onChange = vi.fn();
    render(<RfLinkForm link={link()} onChange={onChange} onDelete={vi.fn()} {...catalogueProps} />);

    fireEvent.click(screen.getByText("+ Emission"));

    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({
        emissions: [
          expect.objectContaining({
            recording: expect.objectContaining({ recording_id: "", version: 1 }),
            start_offset: "PT0S",
            duration_override: null,
          }),
        ],
      }),
    );
  });

  it("editing start offset and duration override round-trips through onChange", () => {
    const emission = {
      id: "e1",
      recording: { recording_id: "rec-1", version: 1, note: null },
      start_offset: "PT0S",
      duration_override: null,
      gain_offset_db: 0,
      loop: false,
      notes: null,
    };
    const onChange = vi.fn();
    render(
      <RfLinkForm
        link={link({ emissions: [emission] })}
        onChange={onChange}
        onDelete={vi.fn()}
        {...catalogueProps}
      />,
    );

    fireEvent.change(screen.getByLabelText("Start offset"), { target: { value: "PT30S" } });
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({
        emissions: [expect.objectContaining({ start_offset: "PT30S" })],
      }),
    );

    fireEvent.change(screen.getByLabelText("Duration override"), { target: { value: "PT5S" } });
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({
        emissions: [expect.objectContaining({ duration_override: "PT5S" })],
      }),
    );
  });

  it("clearing duration override sets it back to null, not an empty string", () => {
    const emission = {
      id: "e1",
      recording: { recording_id: "rec-1", version: 1, note: null },
      start_offset: "PT0S",
      duration_override: "PT5S",
      gain_offset_db: 0,
      loop: false,
      notes: null,
    };
    const onChange = vi.fn();
    render(
      <RfLinkForm
        link={link({ emissions: [emission] })}
        onChange={onChange}
        onDelete={vi.fn()}
        {...catalogueProps}
      />,
    );

    fireEvent.change(screen.getByLabelText("Duration override"), { target: { value: "" } });

    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({
        emissions: [expect.objectContaining({ duration_override: null })],
      }),
    );
  });
});
