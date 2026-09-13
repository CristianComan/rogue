/**
 * Hand-written types mirroring backend/rogue/compiler/models.py — the
 * compiler/scheduler artifacts, analogous in spirit to domain/types.ts for
 * the scenario domain. Same conventions: UUIDs are strings, timestamps are
 * ISO8601 UTC strings.
 */

import type { RecordingReference } from "./types";

// mirrors backend/rogue/compiler/models.py:RealizedFrequencyEvent
export interface RealizedFrequencyEvent {
  link_id: string;
  at_seconds: number;
  frequency_hz: number;
  transition_type: "channel_switch" | "band_switch";
  reason: string;
  seed_context: number | null;
}

// mirrors backend/rogue/compiler/models.py:CompositeChannel
export interface CompositeChannel {
  mission_id: string;
  link_id: string;
  role: "c2" | "telemetry" | "video" | "data";
  emission_id: string;
  center_frequency_hz: number;
  bandwidth_hz: number;
  gain_offset_db: number;
  recording: RecordingReference;
  // Coherent-group allocation fields (ADR-012) — null for an ordinary,
  // non-coherent channel; set together for one array element's entry when
  // the owning link is part of a TDOA/AOA_DOA coherent group.
  coherent_group_id: string | null;
  array_element_receiver_id: string | null;
  phase_offset_rad: number | null;
  delay_offset_s: number | null;
}

// mirrors backend/rogue/compiler/models.py:RfWindow
export interface RfWindow {
  id: string;
  window_key: string;
  start_seconds: number;
  end_seconds: number;
  center_frequency_hz: number;
  bandwidth_hz: number;
  channels: CompositeChannel[];
}

// mirrors backend/rogue/compiler/models.py:PhysicalTxChannelCapability
export interface PhysicalTxChannelCapability {
  device_id: string;
  channel_index: number;
  device_family: "x440" | "air7311" | "simulated_generic";
  tunable_ranges_hz: [number, number][];
  max_usable_bandwidth_hz: number;
  max_sample_rate_hz: number;
}

// mirrors backend/rogue/compiler/models.py:HardwareCapabilityProfile
export interface HardwareCapabilityProfile {
  id: string;
  channels: PhysicalTxChannelCapability[];
}

// mirrors backend/rogue/compiler/models.py:Allocation
export interface Allocation {
  window_key: string;
  start_seconds: number;
  end_seconds: number;
  device_id: string;
  channel_index: number;
  is_migration: boolean;
}

// mirrors backend/rogue/compiler/models.py:SafetyPolicyOutcome
export interface SafetyPolicyOutcome {
  tx_authorized: boolean;
  notes: string | null;
}

// mirrors backend/rogue/domain/validation.py:ValidationSeverity
export type ValidationSeverity = "warning" | "blocking";

// mirrors backend/rogue/compiler/models.py:CompilerFinding
export interface CompilerFinding {
  severity: ValidationSeverity;
  code: string;
  message: string;
  path: string;
}

// mirrors backend/rogue/compiler/models.py:RecordingManifestEntry
export interface RecordingManifestEntry {
  recording_id: string;
  version: number;
  sha256_metadata: string;
  sha256_data: string;
}

// mirrors backend/rogue/compiler/models.py:ReplayPlan
export interface ReplayPlan {
  id: string;
  scenario_id: string;
  scenario_version_number: number;
  compiler_version: string;
  compiled_at: string;
  duration_s: number;
  capability_profile: HardwareCapabilityProfile;
  recording_manifest: RecordingManifestEntry[];
  realized_frequency_events: RealizedFrequencyEvent[];
  rf_windows: RfWindow[];
  allocations: Allocation[];
  safety_policy_outcome: SafetyPolicyOutcome;
  findings: CompilerFinding[];
}

/** One physical channel's identity, used as a stable key/label across the Replay page. */
export function channelKey(deviceId: string, channelIndex: number): string {
  return `${deviceId}:${channelIndex}`;
}

/** Every distinct (device_id, channel_index) pair a plan allocates to, in allocation order. */
export function physicalChannelsInPlan(
  plan: ReplayPlan,
): { device_id: string; channel_index: number }[] {
  const seen = new Set<string>();
  const result: { device_id: string; channel_index: number }[] = [];
  for (const allocation of plan.allocations) {
    const key = channelKey(allocation.device_id, allocation.channel_index);
    if (seen.has(key)) continue;
    seen.add(key);
    result.push({ device_id: allocation.device_id, channel_index: allocation.channel_index });
  }
  return result;
}

export interface ActiveWindow {
  allocation: Allocation;
  window: RfWindow;
  /** Every logical emission sharing this one physical channel's wideband window right now (ADR-003). */
  channels: CompositeChannel[];
}

/**
 * The RfWindow a physical channel is carrying at `runElapsedSeconds`,
 * resolved via the plan's Allocation spans — the replay-time analogue of
 * domain/spectrumStrip.ts:activeEmissionAt, which resolves the same
 * question from authored emission offsets instead of a compiled
 * allocation. A window's `channels` can hold more than one entry: rule 4
 * lets several logical emissions share one wideband physical TX channel.
 */
export function activeWindowAt(
  plan: ReplayPlan,
  deviceId: string,
  channelIndex: number,
  runElapsedSeconds: number,
): ActiveWindow | null {
  const allocation = plan.allocations.find(
    (a) =>
      a.device_id === deviceId &&
      a.channel_index === channelIndex &&
      runElapsedSeconds >= a.start_seconds &&
      runElapsedSeconds < a.end_seconds,
  );
  if (!allocation) return null;

  const window = plan.rf_windows.find((w) => w.window_key === allocation.window_key);
  return window ? { allocation, window, channels: window.channels } : null;
}
