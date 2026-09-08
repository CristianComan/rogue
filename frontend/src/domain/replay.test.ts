import { describe, expect, it } from "vitest";
import { activeWindowAt, physicalChannelsInPlan } from "./replay";
import type { Allocation, CompositeChannel, ReplayPlan, RfWindow } from "./replay";

function compositeChannel(overrides: Partial<CompositeChannel> = {}): CompositeChannel {
  return {
    mission_id: "m1",
    link_id: "l1",
    role: "c2",
    emission_id: "e1",
    center_frequency_hz: 2_437_000_000,
    bandwidth_hz: 20_000_000,
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
    center_frequency_hz: 2_437_000_000,
    bandwidth_hz: 20_000_000,
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

describe("physicalChannelsInPlan", () => {
  it("returns one entry per distinct (device_id, channel_index) pair", () => {
    const p = plan({
      allocations: [
        allocation({ device_id: "x440-1", channel_index: 0 }),
        allocation({ device_id: "x440-1", channel_index: 0, start_seconds: 100, end_seconds: 200 }),
        allocation({ device_id: "x440-1", channel_index: 1 }),
      ],
    });
    expect(physicalChannelsInPlan(p)).toEqual([
      { device_id: "x440-1", channel_index: 0 },
      { device_id: "x440-1", channel_index: 1 },
    ]);
  });

  it("returns an empty array for a plan with no allocations", () => {
    expect(physicalChannelsInPlan(plan({ allocations: [] }))).toEqual([]);
  });
});

describe("activeWindowAt", () => {
  it("resolves the window/channels active on a device+channel at a given run time", () => {
    const p = plan();
    const active = activeWindowAt(p, "x440-1", 0, 50);
    expect(active).not.toBeNull();
    expect(active!.window.window_key).toBe("w1");
    expect(active!.channels).toHaveLength(1);
    expect(active!.allocation.device_id).toBe("x440-1");
  });

  it("returns null outside any allocation's time span", () => {
    const p = plan({ allocations: [allocation({ start_seconds: 0, end_seconds: 10 })] });
    expect(activeWindowAt(p, "x440-1", 0, 50)).toBeNull();
  });

  it("returns null for a device/channel with no allocation at all", () => {
    const p = plan();
    expect(activeWindowAt(p, "air7311-2", 3, 50)).toBeNull();
  });

  it("returns every composite channel sharing the window (ADR-003 composite windows)", () => {
    const p = plan({
      rf_windows: [
        window({
          channels: [compositeChannel({ link_id: "l1" }), compositeChannel({ link_id: "l2" })],
        }),
      ],
    });
    const active = activeWindowAt(p, "x440-1", 0, 50);
    expect(active!.channels.map((c) => c.link_id)).toEqual(["l1", "l2"]);
  });
});
