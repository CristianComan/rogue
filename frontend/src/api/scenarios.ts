/**
 * One function per backend endpoint (backend/rogue/api/scenarios.py).
 * Components must call these, never src/api/client.ts directly.
 */

import { newIdempotencyKey, request } from "./client";
import type {
  DroneMission,
  GeoPolygon,
  RecordingReference,
  Receiver,
  Scenario,
  ScenarioContent,
  ScenarioDraft,
  ScenarioVersion,
  TimelineEvent,
  ValidationFinding,
  Zone,
} from "../domain/types";

export interface CreateScenarioRequest {
  name: string;
  owner: string;
  tags?: string[];
  coordinate_system?: string;
  area_of_operation: GeoPolygon;
  variables?: Record<string, unknown>;
}

export interface ListScenariosParams {
  owner?: string;
  tag?: string;
  name_contains?: string;
  limit?: number;
  offset?: number;
}

/** Content fields for create/update — same shape as ScenarioContent, plus author. */
export type DraftContentInput = Partial<ScenarioContent> & { author: string };

export interface CreateDraftRequest extends DraftContentInput {
  base_version_id?: string | null;
}

export interface UpdateDraftRequest extends DraftContentInput {
  expected_revision: number;
}

export interface CloneRequest {
  name: string;
  owner: string;
  source_version_number?: number;
}

export interface CloneResponse {
  scenario_id: string;
  draft_id: string;
}

function fullContent(input: DraftContentInput): ScenarioContent & { author: string } {
  return {
    author: input.author,
    zones: input.zones ?? [],
    missions: input.missions ?? [],
    receivers: input.receivers ?? [],
    timeline_events: input.timeline_events ?? [],
    recordings: input.recordings ?? [],
  };
}

export function createScenario(body: CreateScenarioRequest): Promise<Scenario> {
  return request<Scenario>("/scenarios", {
    method: "POST",
    body,
    idempotencyKey: newIdempotencyKey(),
  });
}

export function listScenarios(params: ListScenariosParams = {}): Promise<Scenario[]> {
  return request<Scenario[]>("/scenarios", { query: params });
}

export function getScenario(scenarioId: string): Promise<Scenario> {
  return request<Scenario>(`/scenarios/${scenarioId}`);
}

export function createDraft(scenarioId: string, body: CreateDraftRequest): Promise<ScenarioDraft> {
  return request<ScenarioDraft>(`/scenarios/${scenarioId}/drafts`, {
    method: "POST",
    body: { ...fullContent(body), base_version_id: body.base_version_id ?? null },
    idempotencyKey: newIdempotencyKey(),
  });
}

export function getDraft(scenarioId: string, draftId: string): Promise<ScenarioDraft> {
  return request<ScenarioDraft>(`/scenarios/${scenarioId}/drafts/${draftId}`);
}

/** Throws ConflictError (409) if `expected_revision` doesn't match the stored revision. */
export function updateDraft(
  scenarioId: string,
  draftId: string,
  body: UpdateDraftRequest,
): Promise<ScenarioDraft> {
  return request<ScenarioDraft>(`/scenarios/${scenarioId}/drafts/${draftId}`, {
    method: "PUT",
    body: { ...fullContent(body), expected_revision: body.expected_revision },
  });
}

export function validateDraft(scenarioId: string, draftId: string): Promise<ValidationFinding[]> {
  return request<ValidationFinding[]>(`/scenarios/${scenarioId}/drafts/${draftId}/validate`, {
    method: "POST",
  });
}

/** Throws PublishBlockedError (422) if the draft has BLOCKING validation findings. */
export function publishDraft(scenarioId: string, draftId: string): Promise<ScenarioVersion> {
  return request<ScenarioVersion>(`/scenarios/${scenarioId}/drafts/${draftId}/publish`, {
    method: "POST",
    idempotencyKey: newIdempotencyKey(),
  });
}

export function listVersions(scenarioId: string): Promise<ScenarioVersion[]> {
  return request<ScenarioVersion[]>(`/scenarios/${scenarioId}/versions`);
}

export function getVersion(scenarioId: string, versionNumber: number): Promise<ScenarioVersion> {
  return request<ScenarioVersion>(`/scenarios/${scenarioId}/versions/${versionNumber}`);
}

export function cloneScenario(scenarioId: string, body: CloneRequest): Promise<CloneResponse> {
  return request<CloneResponse>(`/scenarios/${scenarioId}/clone`, {
    method: "POST",
    body,
    idempotencyKey: newIdempotencyKey(),
  });
}

// Re-exported so callers only need one import for the common content types.
export type { DroneMission, Receiver, TimelineEvent, RecordingReference, Zone };
