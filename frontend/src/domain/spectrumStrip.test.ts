import { describe, expect, it } from "vitest";
import { currentFrequencyHz } from "./spectrumStrip";
import type { DroneRfLink } from "./types";

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
