import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { Waterfall } from "./Waterfall";
import { ScenarioTimeProvider } from "../../state/scenarioTimeContext";
import type { DroneRfLink, IQRecording, RfEmission, SpectrogramResponse } from "../../domain/types";

const { getSpectrogramMock } = vi.hoisted(() => ({ getSpectrogramMock: vi.fn() }));
vi.mock("../../api/recordings", () => ({ getSpectrogram: getSpectrogramMock }));

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
    expect(getSpectrogramMock).not.toHaveBeenCalled();
  });

  it("shows 'silence' for an explicit silence span, without fetching", () => {
    renderWaterfall(link({ emissions: [emission({ recording: null })] }));
    expect(screen.getByText(/silence/i)).toBeInTheDocument();
    expect(getSpectrogramMock).not.toHaveBeenCalled();
  });

  it("fetches the spectrogram for the active emission's recording and renders a canvas", async () => {
    const result: SpectrogramResponse = {
      time_offsets_s: [0],
      freq_offsets_hz: [-1000, 0, 1000],
      magnitude_db: [[-80, -20, -80]],
    };
    getSpectrogramMock.mockResolvedValue(result);

    renderWaterfall(link());

    await waitFor(() => expect(getSpectrogramMock).toHaveBeenCalledWith("rec-1", 0, 2));
    expect(screen.getByTestId("waterfall-canvas-l1")).toBeInTheDocument();
  });
});
