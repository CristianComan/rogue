/**
 * One function per backend endpoint (backend/rogue/api/recordings.py, M4).
 * Components must call these, never src/api/client.ts directly — same rule
 * as src/api/scenarios.ts, which this mirrors.
 */

import { request } from "./client";
import type { AccessClassification, IQRecording, SpectrogramResponse } from "../domain/types";

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

/**
 * A bounded time/frequency dB preview — matches GET
 * /recordings/{id}/spectrogram, which range-reads only this window's bytes
 * server-side, never the full recording.
 */
export function getSpectrogram(
  recordingId: string,
  windowStartS: number,
  windowDurationS: number,
  fftSize?: number,
): Promise<SpectrogramResponse> {
  return request<SpectrogramResponse>(`/recordings/${recordingId}/spectrogram`, {
    query: {
      window_start_s: windowStartS,
      window_duration_s: windowDurationS,
      ...(fftSize !== undefined ? { fft_size: fftSize } : {}),
    },
  });
}
