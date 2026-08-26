/**
 * Pure helpers for the Spectrum Resource View preview. This reads *authored*
 * RfBand/FrequencyBehaviour data only — there is no RF Environment Compiler
 * yet (M5/M6), so this is explicitly a preview of intent, not a compiled or
 * conflict-checked spectrum plan. The UI must label it as such.
 */

import { durationToSeconds } from "./duration";
import type { DroneRfLink } from "./types";

/**
 * The frequency a link would be on at `scenarioTimeSeconds`, per its
 * authored `scripted_changes` (latest change at-or-before the given time),
 * or the band's minimum frequency if none have "fired" yet / mode isn't
 * scripted.
 */
export function currentFrequencyHz(link: DroneRfLink, scenarioTimeSeconds: number): number {
  if (link.frequency_behaviour.mode !== "scripted") {
    return link.band.freq_min_hz;
  }
  const changes = [...link.frequency_behaviour.scripted_changes].sort(
    (a, b) => durationToSeconds(a.at_offset) - durationToSeconds(b.at_offset),
  );

  let current = link.band.freq_min_hz;
  for (const change of changes) {
    if (durationToSeconds(change.at_offset) > scenarioTimeSeconds) break;
    current = change.frequency_hz;
  }
  return current;
}
