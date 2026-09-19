import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Waterfall } from "./Waterfall";
import { ScenarioTimeProvider } from "../../state/scenarioTimeContext";
import type { DroneRfLink, IQRecording, RfEmission } from "../../domain/types";

function emission(overrides: Partial<RfEmission> = {}): RfEmission {
  return {
    id: "e1",
    recording: { recording_id: "rec-1", version: 1, note: null },
    start_offset: "PT0S",
    duration_override: "PT10S",
    gain_offset_db: 0,
    loop: false,
    notes: null,
    ...overrides,
  };
}

function link(overrides: Partial<DroneRfLink> = {}): DroneRfLink {
  return {
    id: "l1",
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
    emissions: [emission()],
    resource_preference: null,
    ...overrides,
  };
}

function recording(overrides: Partial<IQRecording> = {}): IQRecording {
  return {
    id: "rec-1",
    version: 1,
    metadata_object_key: "k.sigmf-meta",
    data_object_key: "k.sigmf-data",
    sha256_metadata: "a".repeat(64),
    sha256_data: "a".repeat(64),
    sample_format: "cf32_le",
    sample_rate_hz: 1_000_000,
    sample_count: 1_000_000,
    duration_s: 10,
    center_frequency_hz: null,
    kind: "signal",
    overview_spectrogram: {
      time_offsets_s: [0, 5],
      freq_offsets_hz: [-1000, 0, 1000],
      magnitude_db: [
        [-80, -20, -80],
        [-80, -20, -80],
      ],
    },
    provenance: null,
    access_classification: "restricted",
    allowed_use_constraints: [],
    allowed_frequency_min_hz: null,
    allowed_frequency_max_hz: null,
    extra_sigmf_fields: {},
    ...overrides,
  };
}

function renderWaterfall(l: DroneRfLink, catalogue: IQRecording[] = []) {
  return render(
    <ScenarioTimeProvider maxSeconds={100}>
      <Waterfall link={l} missionName="recon-1" catalogue={catalogue} />
    </ScenarioTimeProvider>,
  );
}

describe("Waterfall", () => {
  it("shows 'no active emission' when nothing is scheduled at the current time", () => {
    renderWaterfall(link({ emissions: [emission({ start_offset: "PT50S" })] }));
    expect(screen.getByText(/no active emission/i)).toBeInTheDocument();
  });

  it("shows 'silence' for an explicit silence span", () => {
    renderWaterfall(link({ emissions: [emission({ recording: null })] }));
    expect(screen.getByText(/silence/i)).toBeInTheDocument();
  });

  it("shows a not-found message when the active recording isn't in the catalogue", () => {
    renderWaterfall(link(), []);
    expect(screen.getByText(/not found in catalogue/i)).toBeInTheDocument();
  });

  it("shows a no-overview message for a catalogue recording with no overview computed", () => {
    renderWaterfall(link(), [recording({ overview_spectrogram: null })]);
    expect(screen.getByText(/no spectrogram overview/i)).toBeInTheDocument();
  });

  it("renders a canvas from the recording's precomputed overview, synchronously", () => {
    renderWaterfall(link(), [recording()]);
    expect(screen.getByTestId("waterfall-canvas-l1")).toBeInTheDocument();
  });
});
