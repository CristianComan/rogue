/**
 * Builds the Signal Knowledge Gantt-timeline rows — one row per RF link
 * across every mission, laid out against a fixed 0..maxSeconds axis so the
 * playhead (driven by the single scenarioTimeContext clock, rule 14) is a
 * pure percentage with no per-row scroll state of its own. Replaces the
 * earlier split view (SignalLinksListEditor table + SpectrumStrip's linear
 * bars) with one authored-intent picture: what each link is scheduled to
 * transmit, and when.
 *
 * Every value here is read straight off DroneRfLink/RfEmission/
 * FrequencyBehaviour (backend/rogue/domain/rf.py) or IQRecording
 * (backend/rogue/domain/recording.py) — nothing is invented. Two
 * presentation-only choices are made because the domain model has no
 * equivalent field: a per-mission accent color (cycled from a fixed oklch
 * palette, purely so a row's bars are visually traceable to its owning
 * mission) and a behaviour-mode -> Tone mapping (purely a badge color, the
 * mode string itself is shown verbatim).
 */

import { durationToSeconds } from "./duration";
import type {
  DroneMission,
  FrequencySwitchingMode,
  IQRecording,
  RfEmission,
  RfLinkRole,
} from "./types";
import type { Tone } from "../styles/tokens";

const MISSION_COLOR_HUES = [245, 30, 155, 300, 60, 200];

function colorForMission(missions: DroneMission[], missionId: string): string {
  const index = missions.findIndex((m) => m.id === missionId);
  const hue = MISSION_COLOR_HUES[Math.max(0, index) % MISSION_COLOR_HUES.length];
  return `oklch(0.6 0.15 ${hue})`;
}

const BEHAVIOUR_TONE: Record<FrequencySwitchingMode, Tone> = {
  scripted: "info",
  mission_triggered: "warn",
  probabilistic_adaptive: "warn",
  external_state_triggered: "mute",
};

/** mm:ss, scenario-authoring convention (not wall-clock — see RunHeader's formatElapsed for the run-time equivalent). */
export function formatAxisTime(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m.toString().padStart(2, "0")}:${s.toString().padStart(2, "0")}`;
}

function mhz(hz: number): string {
  return (hz / 1e6).toFixed(3);
}

export interface TimelineEmissionBlock {
  emissionId: string;
  leftPct: number;
  widthPct: number;
  label: string;
  title: string;
  durationResolved: boolean;
}

export interface TimelineChangeTick {
  key: string;
  leftPct: number;
  isBandSwitch: boolean;
  label: string;
  title: string;
}

export interface LinkTimelineRow {
  linkId: string;
  missionId: string;
  missionName: string;
  role: RfLinkRole;
  color: string;
  bandLabel: string;
  channelsLabel: string;
  behaviourMode: FrequencySwitchingMode;
  behaviourTone: Tone;
  emissions: TimelineEmissionBlock[];
  changes: TimelineChangeTick[];
}

/**
 * The end of `emission`'s bar, in scenario seconds — mirrors
 * domain/spectrumStrip.ts:activeEmissionAt's own effective-duration
 * resolution (duration_override, else the referenced recording's real
 * duration_s from the catalogue). A `loop` emission has no defined end (it
 * repeats indefinitely once started), so its bar is drawn to the end of the
 * visible axis; `durationResolved: false` on the returned block distinguishes
 * that — and the genuinely-unresolvable case (recording not yet loaded into
 * `catalogue`) — from a real, known-duration emission.
 */
function resolveEmissionSpan(
  emission: RfEmission,
  startSeconds: number,
  maxSeconds: number,
  catalogue: IQRecording[],
): { endSeconds: number; durationResolved: boolean } {
  if (emission.loop) {
    return { endSeconds: maxSeconds, durationResolved: false };
  }
  if (emission.duration_override !== null) {
    return {
      endSeconds: startSeconds + durationToSeconds(emission.duration_override),
      durationResolved: true,
    };
  }
  if (emission.recording) {
    const recording = catalogue.find(
      (r) => r.id === emission.recording!.recording_id && r.version === emission.recording!.version,
    );
    if (recording) {
      return { endSeconds: startSeconds + recording.duration_s, durationResolved: true };
    }
  }
  return { endSeconds: maxSeconds, durationResolved: false };
}

function recordingLabel(recording: IQRecording | undefined, fallbackId: string): string {
  if (!recording) return fallbackId.slice(0, 8);
  const basename = recording.metadata_object_key.split("/").pop() ?? recording.metadata_object_key;
  return basename.replace(/\.sigmf-meta$/i, "");
}

export function buildLinkTimelineRows(
  missions: DroneMission[],
  maxSeconds: number,
  catalogue: IQRecording[],
): LinkTimelineRow[] {
  const rows: LinkTimelineRow[] = [];

  for (const mission of missions) {
    for (const link of mission.rf_links) {
      const emissions: TimelineEmissionBlock[] = link.emissions.map((emission) => {
        const startSeconds = durationToSeconds(emission.start_offset);
        const { endSeconds, durationResolved } = resolveEmissionSpan(
          emission,
          startSeconds,
          maxSeconds,
          catalogue,
        );
        const leftPct = (startSeconds / maxSeconds) * 100;
        const widthPct = Math.max(0.5, ((endSeconds - startSeconds) / maxSeconds) * 100);

        let label: string;
        let title: string;
        if (!emission.recording) {
          label = "silence";
          title = `${link.role} off-air ${formatAxisTime(startSeconds)}–${formatAxisTime(endSeconds)}`;
        } else {
          const recording = catalogue.find(
            (r) =>
              r.id === emission.recording!.recording_id &&
              r.version === emission.recording!.version,
          );
          const name = recordingLabel(recording, emission.recording.recording_id);
          label = `${name} · ${emission.gain_offset_db.toFixed(0)} dB${emission.loop ? " · loop" : ""}`;
          title = `${link.role} ${formatAxisTime(startSeconds)}–${
            durationResolved ? formatAxisTime(endSeconds) : "?"
          } · ${name}`;
        }

        return { emissionId: emission.id, leftPct, widthPct, label, title, durationResolved };
      });

      const changes: TimelineChangeTick[] =
        link.frequency_behaviour.mode === "scripted"
          ? link.frequency_behaviour.scripted_changes.map((change, i) => {
              const atSeconds = durationToSeconds(change.at_offset);
              const isBandSwitch = change.transition_type === "band_switch";
              return {
                key: `${link.id}:${i}`,
                leftPct: (atSeconds / maxSeconds) * 100,
                isBandSwitch,
                label: isBandSwitch ? `→ ${mhz(change.frequency_hz)}` : mhz(change.frequency_hz),
                title: `${isBandSwitch ? "Band switch" : "Channel switch"} @ ${formatAxisTime(atSeconds)} → ${mhz(change.frequency_hz)} MHz`,
              };
            })
          : [];

      rows.push({
        linkId: link.id,
        missionId: mission.id,
        missionName: mission.name,
        role: link.role,
        color: colorForMission(missions, mission.id),
        bandLabel: `${mhz(link.band.freq_min_hz)}–${mhz(link.band.freq_max_hz)} MHz`,
        channelsLabel:
          link.band.allowed_channels_hz.length > 0
            ? link.band.allowed_channels_hz.map((hz) => Math.round(hz / 1e6)).join(" / ")
            : "—",
        behaviourMode: link.frequency_behaviour.mode,
        behaviourTone: BEHAVIOUR_TONE[link.frequency_behaviour.mode],
        emissions,
        changes,
      });
    }
  }

  return rows;
}
