/**
 * Flattens the per-mission RfLink tree into one row per link, for the
 * Signal Knowledge panel's cross-mission table — scenario content nests
 * DroneRfLink under DroneMission, but an operator reasoning about "what
 * transmits and when" wants to see every link at once, not one mission at a
 * time.
 */

import { currentFrequencyHz } from "./spectrumStrip";
import type { DroneMission, DroneRfLink, RfLinkRole } from "./types";

export interface SignalLinkRow {
  missionId: string;
  missionName: string;
  linkId: string;
  role: RfLinkRole;
  freqMinHz: number;
  freqMaxHz: number;
  currentFrequencyHz: number;
  behaviourMode: DroneRfLink["frequency_behaviour"]["mode"];
  emissionCount: number;
}

export function flattenLinks(
  missions: DroneMission[],
  scenarioTimeSeconds: number,
): SignalLinkRow[] {
  const rows: SignalLinkRow[] = [];
  for (const mission of missions) {
    for (const link of mission.rf_links) {
      rows.push({
        missionId: mission.id,
        missionName: mission.name,
        linkId: link.id,
        role: link.role,
        freqMinHz: link.band.freq_min_hz,
        freqMaxHz: link.band.freq_max_hz,
        currentFrequencyHz: currentFrequencyHz(link, scenarioTimeSeconds),
        behaviourMode: link.frequency_behaviour.mode,
        emissionCount: link.emissions.length,
      });
    }
  }
  return rows;
}
