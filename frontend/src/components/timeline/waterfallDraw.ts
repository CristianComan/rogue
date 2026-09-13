/**
 * Canvas rendering shared by the Development page's per-link Waterfall
 * (Waterfall.tsx) and the Replay page's per-physical-channel tile
 * (components/replay/ReplayChannelTile.tsx) — both draw the same thing (a
 * SpectrogramOverview heatmap plus a moving playhead), just resolved from
 * different data (an authored RfEmission vs. a compiled Allocation).
 * Extracted so neither copy drifts from the other.
 */

import type { SpectrogramOverview } from "../../domain/types";

/** Blue (quiet) -> yellow -> red (loud), normalized per-recording min/max. */
export function colorFor(value: number, min: number, max: number): string {
  const t = max > min ? Math.max(0, Math.min(1, (value - min) / (max - min))) : 0;
  const hue = 240 - 240 * t; // 240 = blue, 0 = red
  return `hsl(${hue}, 85%, ${25 + t * 35}%)`;
}

export function drawWaterfall(
  canvas: HTMLCanvasElement,
  overview: SpectrogramOverview,
  playheadFraction: number,
  playheadColor = "#b85e17",
): void {
  const ctx = canvas.getContext("2d");
  if (!ctx) return;
  ctx.clearRect(0, 0, canvas.width, canvas.height);

  const timeBins = overview.magnitude_db.length;
  const freqBins = overview.freq_offsets_hz.length;
  if (timeBins === 0 || freqBins === 0) return;

  let min = Infinity;
  let max = -Infinity;
  for (const row of overview.magnitude_db) {
    for (const v of row) {
      if (v < min) min = v;
      if (v > max) max = v;
    }
  }

  const cellWidth = canvas.width / timeBins;
  const cellHeight = canvas.height / freqBins;
  for (let t = 0; t < timeBins; t++) {
    for (let f = 0; f < freqBins; f++) {
      // Row 0 is the earliest time bin; freq index 0 is the lowest
      // (fftshift'd) frequency — flip vertically so low frequency draws at
      // the bottom, matching how waterfalls are conventionally read.
      const y = canvas.height - (f + 1) * cellHeight;
      ctx.fillStyle = colorFor(overview.magnitude_db[t][f], min, max);
      ctx.fillRect(t * cellWidth, y, cellWidth + 1, cellHeight + 1);
    }
  }

  const playheadX = Math.max(0, Math.min(1, playheadFraction)) * canvas.width;
  ctx.strokeStyle = playheadColor;
  ctx.lineWidth = 2;
  ctx.beginPath();
  ctx.moveTo(playheadX, 0);
  ctx.lineTo(playheadX, canvas.height);
  ctx.stroke();
}
