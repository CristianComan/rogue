import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ReplayChannelTile } from "./ReplayChannelTile";
import type { Allocation, CompositeChannel, ReplayPlan, RfWindow } from "../../domain/replay";
import type { IQRecording } from "../../domain/types";

function compositeChannel(overrides: Partial<CompositeChannel> = {}): CompositeChannel {
  return {
    mission_id: "m1",
    link_id: "l1",
    role: "video",
    emission_id: "e1",
    center_frequency_hz: 5_800_000_000,
    bandwidth_hz: 40_000_000,
    gain_offset_db: 0,
    recording: { recording_id: "rec-1", version: 1, note: null },
    coherent_group_id: null,
    array_element_receiver_id: null,
    phase_offset_rad: null,
    delay_offset_s: null,
    ...overrides,
  };
}

function window(overrides: Partial<RfWindow> = {}): RfWindow {
  return {
    id: "w1",
    window_key: "w1",
    start_seconds: 0,
    end_seconds: 100,
    center_frequency_hz: 5_800_000_000,
    bandwidth_hz: 40_000_000,
    channels: [compositeChannel()],
    ...overrides,
  };
}

function allocation(overrides: Partial<Allocation> = {}): Allocation {
  return {
    window_key: "w1",
    start_seconds: 0,
    end_seconds: 100,
    device_id: "x440-1",
    channel_index: 0,
    is_migration: false,
    ...overrides,
  };
}

function plan(overrides: Partial<ReplayPlan> = {}): ReplayPlan {
  return {
    id: "plan-1",
    scenario_id: "scenario-1",
    scenario_version_number: 1,
    compiler_version: "test",
    compiled_at: new Date().toISOString(),
    duration_s: 100,
    capability_profile: { id: "test", channels: [] },
    recording_manifest: [],
    realized_frequency_events: [],
    rf_windows: [window()],
    allocations: [allocation()],
    safety_policy_outcome: { tx_authorized: false, notes: null },
    findings: [],
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

describe("ReplayChannelTile", () => {
  it("shows 'unmapped / idle' when nothing is allocated at the current run time", () => {
    render(
      <ReplayChannelTile
        plan={plan({ allocations: [] })}
        deviceId="x440-1"
        channelIndex={0}
        runElapsedSeconds={50}
        catalogue={[]}
        missions={[]}
        lease={undefined}
        nowMs={0}
        runRunning={false}
      />,
    );
    expect(screen.getByText(/unmapped \/ idle/i)).toBeInTheDocument();
  });

  it("shows the active composite channel's role and frequency", () => {
    render(
      <ReplayChannelTile
        plan={plan()}
        deviceId="x440-1"
        channelIndex={0}
        runElapsedSeconds={50}
        catalogue={[recording()]}
        missions={[]}
        lease={undefined}
        nowMs={0}
        runRunning={false}
      />,
    );
    expect(screen.getByText(/video/i)).toBeInTheDocument();
    expect(screen.getByText(/5800\.000 MHz/)).toBeInTheDocument();
  });

  it("shows a '+N more' hint when several logical channels share the window", () => {
    render(
      <ReplayChannelTile
        plan={plan({
          rf_windows: [
            window({
              channels: [compositeChannel({ link_id: "l1" }), compositeChannel({ link_id: "l2" })],
            }),
          ],
        })}
        deviceId="x440-1"
        channelIndex={0}
        runElapsedSeconds={50}
        catalogue={[recording()]}
        missions={[]}
        lease={undefined}
        nowMs={0}
        runRunning={false}
      />,
    );
    expect(screen.getByText(/\+1 more/)).toBeInTheDocument();
  });

  it("shows the lease countdown when a lease is present", () => {
    render(
      <ReplayChannelTile
        plan={plan()}
        deviceId="x440-1"
        channelIndex={0}
        runElapsedSeconds={50}
        catalogue={[recording()]}
        missions={[]}
        lease={{
          id: "lease-1",
          device_id: "x440-1",
          channel_index: 0,
          run_id: "run-1",
          leased_at: new Date(0).toISOString(),
          expires_at: new Date(10_000).toISOString(),
        }}
        nowMs={0}
        runRunning={false}
      />,
    );
    expect(screen.getByText(/lease 10s/)).toBeInTheDocument();
  });
});
