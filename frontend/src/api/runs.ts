/**
 * One function per backend endpoint (backend/rogue/api/runs.py). Arm/start/
 * stop are idempotency-key gated per that module's own docstring;
 * emergency-stop deliberately is not — it must always be reachable.
 */

import { newIdempotencyKey, request } from "./client";
import type { ScenarioRun } from "../domain/run";

const base = (scenarioId: string, planId: string) =>
  `/scenarios/${scenarioId}/replay-plans/${planId}/runs`;

export function listRuns(scenarioId: string, planId: string): Promise<ScenarioRun[]> {
  return request<ScenarioRun[]>(base(scenarioId, planId));
}

export function getRun(scenarioId: string, planId: string, runId: string): Promise<ScenarioRun> {
  return request<ScenarioRun>(`${base(scenarioId, planId)}/${runId}`);
}

export function createRun(
  scenarioId: string,
  planId: string,
  operator: string,
): Promise<ScenarioRun> {
  return request<ScenarioRun>(base(scenarioId, planId), {
    method: "POST",
    body: { operator },
    idempotencyKey: newIdempotencyKey(),
  });
}

export function armRun(scenarioId: string, planId: string, runId: string): Promise<ScenarioRun> {
  return request<ScenarioRun>(`${base(scenarioId, planId)}/${runId}/arm`, {
    method: "POST",
    idempotencyKey: newIdempotencyKey(),
  });
}

export function startRun(scenarioId: string, planId: string, runId: string): Promise<ScenarioRun> {
  return request<ScenarioRun>(`${base(scenarioId, planId)}/${runId}/start`, {
    method: "POST",
    idempotencyKey: newIdempotencyKey(),
  });
}

export function stopRun(scenarioId: string, planId: string, runId: string): Promise<ScenarioRun> {
  return request<ScenarioRun>(`${base(scenarioId, planId)}/${runId}/stop`, {
    method: "POST",
    idempotencyKey: newIdempotencyKey(),
  });
}

/** Never idempotency-key gated: must always succeed, per CLAUDE.md's safety rules. */
export function emergencyStopRun(
  scenarioId: string,
  planId: string,
  runId: string,
): Promise<ScenarioRun> {
  return request<ScenarioRun>(`${base(scenarioId, planId)}/${runId}/emergency-stop`, {
    method: "POST",
  });
}
