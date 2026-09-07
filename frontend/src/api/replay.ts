/**
 * One function per backend endpoint (backend/rogue/api/replay.py).
 */

import { request } from "./client";
import type { ReplayPlan } from "../domain/replay";

export function listReplayPlans(scenarioId: string): Promise<ReplayPlan[]> {
  return request<ReplayPlan[]>(`/scenarios/${scenarioId}/replay-plans`);
}

export function getReplayPlan(scenarioId: string, planId: string): Promise<ReplayPlan> {
  return request<ReplayPlan>(`/scenarios/${scenarioId}/replay-plans/${planId}`);
}
