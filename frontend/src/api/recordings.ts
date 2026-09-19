/**
 * One function per backend endpoint (backend/rogue/api/recordings.py, M4).
 * Components must call these, never src/api/client.ts directly — same rule
 * as src/api/scenarios.ts, which this mirrors.
 */

import { request } from "./client";
import type { AccessClassification, IQRecording } from "../domain/types";

export interface ListRecordingsParams {
  access_classification?: AccessClassification;
  provenance_contains?: string;
  limit?: number;
  offset?: number;
}

/** Latest version of each catalogue entry — matches GET /recordings. */
export function listRecordings(params: ListRecordingsParams = {}): Promise<IQRecording[]> {
  return request<IQRecording[]>("/recordings", { query: params });
}

export function getRecording(recordingId: string): Promise<IQRecording> {
  return request<IQRecording>(`/recordings/${recordingId}`);
}
