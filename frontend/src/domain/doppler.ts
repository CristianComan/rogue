/**
 * Receiver-to-drone range and range-rate at a scenario time — the geometry
 * an operator needs to reason about Doppler shift on a link before
 * compilation. Deliberately reuses missionEvaluator's evaluateMissionState
 * (sampled twice, at t and t+dt) rather than re-deriving a velocity-vector/
 * bearing projection, so it is automatically correct for every mission
 * template (orbit, holds, before-start) without special-casing each one.
 */

import { haversineDistanceMeters } from "./geojson";
import { evaluateMissionState } from "./missionEvaluator";
import type { DroneMission, Receiver } from "./types";

export interface RangeAndRangeRate {
  rangeM: number;
  /** Positive = receding, negative = closing. */
  rangeRateMps: number;
}

const DEFAULT_DT_SECONDS = 0.5;

export function rangeAndRangeRate(
  receiver: Receiver,
  mission: DroneMission,
  scenarioTimeSeconds: number,
  dtSeconds: number = DEFAULT_DT_SECONDS,
): RangeAndRangeRate {
  const at = evaluateMissionState(mission, scenarioTimeSeconds);
  const afterDt = evaluateMissionState(mission, scenarioTimeSeconds + dtSeconds);

  const rangeAtT = haversineDistanceMeters(receiver.position.coordinates, at.positionLonLat);
  const rangeAtTPlusDt = haversineDistanceMeters(
    receiver.position.coordinates,
    afterDt.positionLonLat,
  );

  return {
    rangeM: rangeAtT,
    rangeRateMps: (rangeAtTPlusDt - rangeAtT) / dtSeconds,
  };
}

export interface DopplerSample {
  scenarioTimeSeconds: number;
  rangeM: number;
  rangeRateMps: number;
}

/** Evenly-sampled range/range-rate series across [0, durationSeconds], for a sparkline. */
export function sampleRangeSeries(
  receiver: Receiver,
  mission: DroneMission,
  durationSeconds: number,
  sampleCount = 40,
): DopplerSample[] {
  if (durationSeconds <= 0 || sampleCount < 2) {
    const single = rangeAndRangeRate(receiver, mission, 0);
    return [{ scenarioTimeSeconds: 0, ...single }];
  }
  const samples: DopplerSample[] = [];
  for (let i = 0; i < sampleCount; i++) {
    const t = (durationSeconds * i) / (sampleCount - 1);
    samples.push({ scenarioTimeSeconds: t, ...rangeAndRangeRate(receiver, mission, t) });
  }
  return samples;
}
