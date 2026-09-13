/**
 * Hand-written types mirroring backend/rogue/domain/run.py — the execution
 * record for a compiled ReplayPlan. Same conventions as domain/types.ts:
 * UUIDs are strings, timestamps are ISO8601 UTC strings.
 */

import type { ValidationSeverity } from "./replay";

// mirrors backend/rogue/domain/run.py:RunStatus
export type RunStatus =
  | "created"
  | "preparing"
  | "prepared"
  | "armed"
  | "running"
  | "stopping"
  | "stopped"
  | "failed"
  | "emergency_stopped";

// mirrors backend/rogue/domain/run.py:DeviceLease
export interface DeviceLease {
  id: string;
  device_id: string;
  channel_index: number;
  run_id: string;
  leased_at: string;
  expires_at: string;
}

// mirrors backend/rogue/domain/run.py:RunEventKind
export type RunEventKind =
  | "reserved"
  | "prefetch_verified"
  | "configured"
  | "armed"
  | "started"
  | "stopped"
  | "emergency_stopped"
  | "lease_renewed"
  | "error";

// mirrors backend/rogue/domain/run.py:RunEvent
export interface RunEvent {
  id: string;
  at: string;
  sequence: number;
  kind: RunEventKind;
  device_id: string | null;
  channel_index: number | null;
  message: string;
  severity: ValidationSeverity;
}

// mirrors backend/rogue/domain/run.py:ScenarioRun
export interface ScenarioRun {
  id: string;
  scenario_id: string;
  replay_plan_id: string;
  operator: string;
  status: RunStatus;
  device_leases: DeviceLease[];
  events: RunEvent[];
  created_at: string;
  updated_at: string;
}

/** The `started`-kind event's timestamp, if the run has reached RUNNING at least once. */
export function startedAt(run: ScenarioRun): string | null {
  return run.events.find((e) => e.kind === "started")?.at ?? null;
}

/** The last `stopped`/`emergency_stopped` event's timestamp, if the run has since stopped. */
export function stoppedAt(run: ScenarioRun): string | null {
  const stopEvents = run.events.filter(
    (e) => e.kind === "stopped" || e.kind === "emergency_stopped",
  );
  if (stopEvents.length === 0) return null;
  return stopEvents.reduce((a, b) => (a.sequence > b.sequence ? a : b)).at;
}
