import { describe, expect, it } from "vitest";
import { buildLinkTimelineRows, formatAxisTime } from "./signalTimeline";
import type { DroneMission, DroneRfLink, IQRecording, RfEmission } from "./types";

function emission(overrides: Partial<RfEmission> = {}): RfEmission {
  return {
    id: "e1",
    recording: { recording_id: "rec-1", version: 1, note: null },
    start_offset: "PT0S",
    duration_override: null,
    gain_offset_db: -6,
    loop: false,
    notes: null,
    ...overrides,
  };
}

function recording(overrides: Partial<IQRecording> = {}): IQRecording {
  return {
    id: "rec-1",
    version: 1,
    metadata_object_key: "urban/uplink_c2.sigmf-meta",
    data_object_key: "urban/uplink_c2.sigmf-data",
    sha256_metadata: "a".repeat(64),
    sha256_data: "a".repeat(64),
    sample_format: "cf32_le",
    sample_rate_hz: 1_000_000,
    sample_count: 1_000_000,
    duration_s: 10,
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
    emissions: [],
    resource_preference: null,
    ...overrides,
  };
}

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
    rf_links: [],
    ...overrides,
  };
}

describe("formatAxisTime", () => {
  it("formats seconds as mm:ss", () => {
    expect(formatAxisTime(0)).toBe("00:00");
    expect(formatAxisTime(65)).toBe("01:05");
    expect(formatAxisTime(600)).toBe("10:00");
  });
});

describe("buildLinkTimelineRows", () => {
  it("derives band and channels labels from real RfBand fields", () => {
    const rows = buildLinkTimelineRows(
      [
        mission({
          rf_links: [
            link({
              band: {
                freq_min_hz: 2_412_000_000,
                freq_max_hz: 2_462_000_000,
                allowed_channels_hz: [2_412_000_000, 2_437_000_000, 2_462_000_000],
              },
            }),
          ],
        }),
      ],
      600,
      [],
    );
    expect(rows[0].bandLabel).toBe("2412.000–2462.000 MHz");
    expect(rows[0].channelsLabel).toBe("2412 / 2437 / 2462");
  });

  it("shows '—' for channels when none are authored", () => {
    const rows = buildLinkTimelineRows([mission({ rf_links: [link()] })], 600, []);
    expect(rows[0].channelsLabel).toBe("—");
  });

  it("resolves an emission's span from duration_override", () => {
    const l = link({
      emissions: [emission({ start_offset: "PT10S", duration_override: "PT30S" })],
    });
    const rows = buildLinkTimelineRows([mission({ rf_links: [l] })], 100, []);
    const e = rows[0].emissions[0];
    expect(e.leftPct).toBeCloseTo(10, 5);
    expect(e.widthPct).toBeCloseTo(30, 5);
    expect(e.durationResolved).toBe(true);
  });

  it("resolves an emission's span from the catalogue when duration_override is unset", () => {
    const l = link({ emissions: [emission({ start_offset: "PT0S", duration_override: null })] });
    const rows = buildLinkTimelineRows([mission({ rf_links: [l] })], 100, [
      recording({ duration_s: 25 }),
    ]);
    const e = rows[0].emissions[0];
    expect(e.widthPct).toBeCloseTo(25, 5);
    expect(e.durationResolved).toBe(true);
  });

  it("draws a looping emission's bar to the end of the axis, marked unresolved", () => {
    const l = link({
      emissions: [emission({ start_offset: "PT0S", duration_override: "PT1S", loop: true })],
    });
    const rows = buildLinkTimelineRows([mission({ rf_links: [l] })], 100, []);
    const e = rows[0].emissions[0];
    expect(e.widthPct).toBeCloseTo(100, 5);
    expect(e.durationResolved).toBe(false);
  });

  it("draws to the axis end and marks unresolved when the recording isn't in the catalogue", () => {
    const l = link({ emissions: [emission({ start_offset: "PT0S", duration_override: null })] });
    const rows = buildLinkTimelineRows([mission({ rf_links: [l] })], 100, []);
    expect(rows[0].emissions[0].durationResolved).toBe(false);
  });

  it("labels an explicit silence emission (recording: null) as silence", () => {
    const l = link({
      emissions: [emission({ recording: null, start_offset: "PT0S", duration_override: "PT5S" })],
    });
    const rows = buildLinkTimelineRows([mission({ rf_links: [l] })], 100, []);
    expect(rows[0].emissions[0].label).toBe("silence");
  });

  it("labels an emission from the catalogue recording's filename, gain and loop flag", () => {
    const l = link({
      emissions: [
        emission({
          start_offset: "PT0S",
          duration_override: "PT5S",
          gain_offset_db: -12,
          loop: true,
        }),
      ],
    });
    const rows = buildLinkTimelineRows([mission({ rf_links: [l] })], 100, [
      recording({ metadata_object_key: "urban/uplink_c2.sigmf-meta" }),
    ]);
    expect(rows[0].emissions[0].label).toBe("uplink_c2 · -12 dB · loop");
  });

  it("only emits change ticks for scripted-mode links", () => {
    const scripted = link({
      id: "l-scripted",
      frequency_behaviour: {
        mode: "scripted",
        scripted_changes: [
          { at_offset: "PT10S", frequency_hz: 2_437_000_000, transition_type: "channel_switch" },
          { at_offset: "PT20S", frequency_hz: 5_800_000_000, transition_type: "band_switch" },
        ],
        mission_trigger_anchor: null,
        random_seed: null,
        mean_dwell_s: null,
        external_trigger_reference: null,
      },
    });
    const adaptive = link({
      id: "l-adaptive",
      frequency_behaviour: {
        mode: "probabilistic_adaptive",
        scripted_changes: [],
        mission_trigger_anchor: null,
        random_seed: 1,
        mean_dwell_s: 5,
        external_trigger_reference: null,
      },
    });
    const rows = buildLinkTimelineRows([mission({ rf_links: [scripted, adaptive] })], 100, []);
    const scriptedRow = rows.find((r) => r.linkId === "l-scripted")!;
    const adaptiveRow = rows.find((r) => r.linkId === "l-adaptive")!;
    expect(scriptedRow.changes).toHaveLength(2);
    expect(scriptedRow.changes[0].isBandSwitch).toBe(false);
    expect(scriptedRow.changes[0].label).toBe("2437.000");
    expect(scriptedRow.changes[1].isBandSwitch).toBe(true);
    expect(scriptedRow.changes[1].label).toBe("→ 5800.000");
    expect(adaptiveRow.changes).toHaveLength(0);
  });

  it("maps each behaviour mode to a display tone", () => {
    const modes = [
      "scripted",
      "mission_triggered",
      "probabilistic_adaptive",
      "external_state_triggered",
    ] as const;
    const rows = buildLinkTimelineRows(
      [
        mission({
          rf_links: modes.map((mode, i) =>
            link({
              id: `l${i}`,
              frequency_behaviour: {
                mode,
                scripted_changes: [],
                mission_trigger_anchor: null,
                random_seed: null,
                mean_dwell_s: null,
                external_trigger_reference: null,
              },
            }),
          ),
        }),
      ],
      100,
      [],
    );
    expect(rows.map((r) => r.behaviourTone)).toEqual(["info", "warn", "warn", "mute"]);
  });

  it("flattens links across multiple missions", () => {
    const rows = buildLinkTimelineRows(
      [
        mission({ id: "m1", rf_links: [link({ id: "l1" })] }),
        mission({ id: "m2", rf_links: [link({ id: "l2" })] }),
      ],
      100,
      [],
    );
    expect(rows.map((r) => r.linkId)).toEqual(["l1", "l2"]);
    expect(rows[0].missionId).toBe("m1");
    expect(rows[1].missionId).toBe("m2");
  });
});
