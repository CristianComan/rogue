import { useEffect, useRef, useState } from "react";
import { getSpectrogram } from "../../api/recordings";
import { durationToSeconds } from "../../domain/duration";
import { activeEmissionAt, currentFrequencyHz } from "../../domain/spectrumStrip";
import type { DroneRfLink, IQRecording, SpectrogramResponse } from "../../domain/types";
import { useScenarioTime } from "../../state/scenarioTimeContext";

const WINDOW_DURATION_S = 2;
const CANVAS_WIDTH = 320;
const CANVAS_HEIGHT = 140;

function mhz(hz: number): string {
  return (hz / 1e6).toFixed(3);
}

/** Blue (quiet) -> yellow -> red (loud), normalized per-fetch min/max. */
function colorFor(value: number, min: number, max: number): string {
  const t = max > min ? Math.max(0, Math.min(1, (value - min) / (max - min))) : 0;
  const hue = 240 - 240 * t; // 240 = blue, 0 = red
  return `hsl(${hue}, 85%, ${25 + t * 35}%)`;
}

function drawSpectrogram(canvas: HTMLCanvasElement, data: SpectrogramResponse): void {
  const ctx = canvas.getContext("2d");
  if (!ctx) return;
  ctx.clearRect(0, 0, canvas.width, canvas.height);

  const timeBins = data.magnitude_db.length;
  const freqBins = data.freq_offsets_hz.length;
  if (timeBins === 0 || freqBins === 0) return;

  let min = Infinity;
  let max = -Infinity;
  for (const row of data.magnitude_db) {
    for (const v of row) {
      if (v < min) min = v;
      if (v > max) max = v;
    }
  }

  const cellWidth = canvas.width / timeBins;
  const cellHeight = canvas.height / freqBins;
  for (let t = 0; t < timeBins; t++) {
    for (let f = 0; f < freqBins; f++) {
      // Row 0 of magnitude_db is the lowest time bin; freq index 0 is the
      // lowest (fftshift'd) frequency — flip vertically so low frequency
      // draws at the bottom, matching how waterfalls are conventionally read.
      const y = canvas.height - (f + 1) * cellHeight;
      ctx.fillStyle = colorFor(data.magnitude_db[t][f], min, max);
      ctx.fillRect(t * cellWidth, y, cellWidth + 1, cellHeight + 1);
    }
  }
}

export interface WaterfallProps {
  link: DroneRfLink;
  missionName: string;
  catalogue: IQRecording[];
}

/**
 * A real time-frequency waterfall of whatever `link` is actually playing
 * right now, computed from the recording's own I/Q bytes (a bounded
 * server-side STFT — see api/recordings.ts:getSpectrogram) rather than a
 * schematic occupancy line (that's SpectrumStrip). The Y-axis is re-centered
 * on the link's live authored frequency (currentFrequencyHz), not the
 * recording's own capture frequency — a display convenience, not a
 * compiled/conflict-checked plan (same disclaimer convention as
 * SpectrumStrip).
 *
 * Fetches are throttled to once per WINDOW_DURATION_S bucket of the active
 * emission, not every animation frame — scenarioTimeContext remains the
 * only requestAnimationFrame owner (CLAUDE.md rule 14).
 */
export function Waterfall({ link, missionName, catalogue }: WaterfallProps) {
  const { scenarioTimeSeconds } = useScenarioTime();
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [data, setData] = useState<SpectrogramResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const emission = activeEmissionAt(link, scenarioTimeSeconds, catalogue);
  const recordingId = emission?.recording?.recording_id ?? null;
  const emissionStart = emission ? durationToSeconds(emission.start_offset) : 0;
  const localTimeS = emission ? scenarioTimeSeconds - emissionStart : 0;
  const windowStartS = recordingId
    ? Math.floor(localTimeS / WINDOW_DURATION_S) * WINDOW_DURATION_S
    : 0;

  useEffect(() => {
    if (!recordingId) {
      setData(null);
      return;
    }
    let cancelled = false;
    setError(null);
    getSpectrogram(recordingId, windowStartS, WINDOW_DURATION_S)
      .then((result) => {
        if (!cancelled) setData(result);
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      });
    return () => {
      cancelled = true;
    };
    // Re-fetches only when the active recording or the WINDOW_DURATION_S
    // bucket changes, not on every scenarioTimeSeconds tick.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [recordingId, windowStartS]);

  useEffect(() => {
    if (canvasRef.current && data) drawSpectrogram(canvasRef.current, data);
  }, [data]);

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
        Waterfall preview — {missionName} · {link.role} · re-centered on {mhz(liveFrequencyHz)} MHz
      </div>
      {!emission && <div style={{ fontSize: 11, color: "#4c5c5e" }}>No active emission.</div>}
      {emission && !recordingId && (
        <div style={{ fontSize: 11, color: "#4c5c5e" }}>Silence — link is off-air.</div>
      )}
      {error && <div style={{ fontSize: 11, color: "crimson" }}>{error}</div>}
      {recordingId && (
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
