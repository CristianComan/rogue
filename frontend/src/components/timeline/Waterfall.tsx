import { useEffect, useRef } from "react";
import { durationToSeconds } from "../../domain/duration";
import { activeEmissionAt, currentFrequencyHz } from "../../domain/spectrumStrip";
import type { DroneRfLink, IQRecording } from "../../domain/types";
import { useScenarioTime } from "../../state/scenarioTimeContext";
import { drawWaterfall } from "./waterfallDraw";

const CANVAS_WIDTH = 320;
const CANVAS_HEIGHT = 140;

function mhz(hz: number): string {
  return (hz / 1e6).toFixed(3);
}

export interface WaterfallProps {
  link: DroneRfLink;
  missionName: string;
  catalogue: IQRecording[];
}

/**
 * A real time-frequency waterfall of whatever `link` is actually playing
 * right now: the whole recording's precomputed overview
 * (`IQRecording.overview_spectrogram`, built once at ingest — see
 * catalogue/spectrogram.py) rendered as a static heatmap, with a moving
 * playhead marking the current position within it. A live per-request STFT
 * was tried first and rejected — at a real drone-corpus sample rate even a
 * short scrub window decodes to hundreds of MB, too expensive to compute
 * synchronously per request. This component is purely synchronous: no
 * fetching, derived entirely from `catalogue` (already loaded by the
 * editor) and `scenarioTimeSeconds`.
 *
 * The Y-axis is re-centered on the link's live authored frequency
 * (`currentFrequencyHz`), not the recording's own capture frequency — a
 * display convenience, not a compiled/conflict-checked plan (same
 * authored-intent-only disclaimer as the Signal Knowledge Gantt timeline).
 */
export function Waterfall({ link, missionName, catalogue }: WaterfallProps) {
  const { scenarioTimeSeconds } = useScenarioTime();
  const canvasRef = useRef<HTMLCanvasElement>(null);

  const emission = activeEmissionAt(link, scenarioTimeSeconds, catalogue);
  const recording = emission?.recording
    ? catalogue.find(
        (r) =>
          r.id === emission.recording!.recording_id && r.version === emission.recording!.version,
      )
    : null;
  const overview = recording?.overview_spectrogram ?? null;

  let playheadFraction = 0;
  if (emission && recording && recording.duration_s > 0) {
    const emissionStart = durationToSeconds(emission.start_offset);
    const localTimeS = scenarioTimeSeconds - emissionStart;
    const positionInRecordingS = emission.loop
      ? localTimeS % recording.duration_s
      : Math.min(localTimeS, recording.duration_s);
    playheadFraction = positionInRecordingS / recording.duration_s;
  }

  useEffect(() => {
    if (canvasRef.current && overview) drawWaterfall(canvasRef.current, overview, playheadFraction);
  }, [overview, playheadFraction]);

  const liveFrequencyHz = currentFrequencyHz(link, scenarioTimeSeconds);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 4, padding: "4px 12px" }}>
      <div
        style={{
          fontSize: 10,
          letterSpacing: "0.04em",
          textTransform: "uppercase",
          color: "#4c5c5e",
        }}
      >
        Waterfall — {missionName} · {link.role} · re-centered on {mhz(liveFrequencyHz)} MHz
      </div>
      {!emission && <div style={{ fontSize: 11, color: "#4c5c5e" }}>No active emission.</div>}
      {emission && !emission.recording && (
        <div style={{ fontSize: 11, color: "#4c5c5e" }}>Silence — link is off-air.</div>
      )}
      {emission && emission.recording && !recording && (
        <div style={{ fontSize: 11, color: "#4c5c5e" }}>Recording not found in catalogue.</div>
      )}
      {emission && recording && !overview && (
        <div style={{ fontSize: 11, color: "#4c5c5e" }}>
          No spectrogram overview for this recording.
        </div>
      )}
      {overview && (
        <canvas
          ref={canvasRef}
          width={CANVAS_WIDTH}
          height={CANVAS_HEIGHT}
          data-testid={`waterfall-canvas-${link.id}`}
          style={{ border: "1px solid #ccc", imageRendering: "pixelated" }}
        />
      )}
    </div>
  );
}
