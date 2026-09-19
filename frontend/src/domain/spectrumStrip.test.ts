import { describe, expect, it } from "vitest";
import { activeEmissionAt, currentFrequencyHz } from "./spectrumStrip";
import type { DroneRfLink, IQRecording, RfEmission } from "./types";

function emission(overrides: Partial<RfEmission> = {}): RfEmission {
  return {
    id: "e1",
    recording: { recording_id: "rec-1", version: 1, note: null },
    start_offset: "PT0S",
    duration_override: null,
    gain_offset_db: 0,
    loop: false,
    notes: null,
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
    duration_s: 1,
    center_frequency_hz: null,
    kind: "signal",
    overview_spectrogram: null,
    provenance: null,
    access_classification: "restricted",
    allowed_use_constraints: [],
    allowed_frequency_min_hz: null,
    allowed_frequency_max_hz: null,
    extra_sigmf_fields: {},
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
    emissions: [],
    resource_preference: null,
    ...overrides,
  };
}

describe("currentFrequencyHz", () => {
  it("returns the band minimum before any scripted change has fired", () => {
    const l = link({
      frequency_behaviour: {
        mode: "scripted",
        scripted_changes: [
          { at_offset: "PT10S", frequency_hz: 2_412_000_000, transition_type: "channel_switch" },
        ],
        mission_trigger_anchor: null,
        random_seed: null,
        mean_dwell_s: null,
        external_trigger_reference: null,
      },
    });
    expect(currentFrequencyHz(l, 5)).toBe(2_400_000_000);
  });

  it("returns the latest fired change's frequency", () => {
    const l = link({
      frequency_behaviour: {
        mode: "scripted",
        scripted_changes: [
          { at_offset: "PT0S", frequency_hz: 2_412_000_000, transition_type: "channel_switch" },
          { at_offset: "PT20S", frequency_hz: 2_437_000_000, transition_type: "channel_switch" },
        ],
        mission_trigger_anchor: null,
        random_seed: null,
        mean_dwell_s: null,
        external_trigger_reference: null,
      },
    });
    expect(currentFrequencyHz(l, 10)).toBe(2_412_000_000);
    expect(currentFrequencyHz(l, 20)).toBe(2_437_000_000);
    expect(currentFrequencyHz(l, 100)).toBe(2_437_000_000);
  });

  it("returns the band minimum for non-scripted modes", () => {
    const l = link({
      frequency_behaviour: {
        mode: "probabilistic_adaptive",
        scripted_changes: [],
        mission_trigger_anchor: null,
        random_seed: 42,
        mean_dwell_s: 5,
        external_trigger_reference: null,
      },
    });
    expect(currentFrequencyHz(l, 500)).toBe(2_400_000_000);
  });
});

describe("activeEmissionAt", () => {
  it("returns null before any emission has started", () => {
    const l = link({ emissions: [emission({ start_offset: "PT10S", duration_override: "PT5S" })] });
    expect(activeEmissionAt(l, 5, [])).toBeNull();
  });

  it("resolves duration from duration_override when set", () => {
    const e = emission({ start_offset: "PT0S", duration_override: "PT5S" });
    const l = link({ emissions: [e] });
    expect(activeEmissionAt(l, 4, [])).toBe(e);
    expect(activeEmissionAt(l, 6, [])).toBeNull();
  });

  it("resolves duration from the catalogue when duration_override is unset", () => {
    const e = emission({ start_offset: "PT0S", duration_override: null });
    const l = link({ emissions: [e] });
    const catalogue = [recording({ duration_s: 3 })];
    expect(activeEmissionAt(l, 2, catalogue)).toBe(e);
    expect(activeEmissionAt(l, 4, catalogue)).toBeNull();
  });

  it("treats an emission as active once started if duration can't be resolved", () => {
    const e = emission({ start_offset: "PT0S", duration_override: null });
    const l = link({ emissions: [e] });
    expect(activeEmissionAt(l, 1_000, [])).toBe(e);
  });

  it("a looping emission is always active once started", () => {
    const e = emission({ start_offset: "PT0S", duration_override: "PT1S", loop: true });
    const l = link({ emissions: [e] });
    expect(activeEmissionAt(l, 10_000, [])).toBe(e);
  });

  it("returns an explicit silence emission (recording: null) as active", () => {
    const e = emission({ recording: null, start_offset: "PT0S", duration_override: "PT5S" });
    const l = link({ emissions: [e] });
    expect(activeEmissionAt(l, 2, [])).toBe(e);
  });

  it("returns null when nothing is scheduled at all", () => {
    const l = link({ emissions: [] });
    expect(activeEmissionAt(l, 0, [])).toBeNull();
  });
});
