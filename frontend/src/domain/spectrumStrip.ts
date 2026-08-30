/**
 * Pure helpers for the Spectrum Resource View preview. This reads *authored*
 * RfBand/FrequencyBehaviour data only — there is no RF Environment Compiler
 * yet (M5/M6), so this is explicitly a preview of intent, not a compiled or
 * conflict-checked spectrum plan. The UI must label it as such.
 */

import { durationToSeconds } from "./duration";
import type { DroneRfLink, IQRecording, RfEmission } from "./types";

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

/**
 * The emission (if any) actively scheduled on `link` at `scenarioTimeSeconds`.
 *
 * Mirrors backend/rogue/spectrum/occupancy.py:active_emission_at exactly,
 * including its conservative fallback: effective duration prefers
 * `duration_override`; otherwise it needs the referenced recording's
 * `duration_s` from `catalogue`. If neither is available, the emission is
 * treated as active once started rather than silently idle. `null` is a
 * normal outcome (nothing scheduled here), not an error.
 */
export function activeEmissionAt(
  link: DroneRfLink,
  scenarioTimeSeconds: number,
  catalogue: IQRecording[],
): RfEmission | null {
  for (const emission of link.emissions) {
    const start = durationToSeconds(emission.start_offset);
    if (scenarioTimeSeconds < start) continue;
    if (emission.loop) return emission;

    let duration: number | null;
    if (emission.duration_override !== null) {
      duration = durationToSeconds(emission.duration_override);
    } else {
      // RfEmission requires duration_override whenever recording is null,
      // so reaching here means emission.recording is set.
      const recording = catalogue.find(
        (r) =>
          r.id === emission.recording!.recording_id && r.version === emission.recording!.version,
      );
      duration = recording ? recording.duration_s : null;
    }

    if (duration === null || scenarioTimeSeconds - start < duration) return emission;
  }
  return null;
}
