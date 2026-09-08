import { useEffect, useRef } from "react";
import { activeWindowAt, type ReplayPlan } from "../../domain/replay";
import type { DeviceLease } from "../../domain/run";
import type { IQRecording } from "../../domain/types";
import { colors, monoFontStack } from "../../styles/tokens";
import { drawWaterfall } from "../timeline/waterfallDraw";

const CANVAS_WIDTH = 260;
const CANVAS_HEIGHT = 120;

function mhz(hz: number): string {
  return (hz / 1e6).toFixed(3);
}

/**
 * One physical TX channel's live waterfall on the Replay page — the
 * per-physical-channel counterpart to the Development page's per-link
 * Waterfall (components/timeline/Waterfall.tsx). Resolves what the channel
 * is actually carrying from the compiled ReplayPlan's Allocation spans
 * (domain/replay.ts:activeWindowAt) rather than from authored emission
 * offsets, and shares the same canvas draw code (waterfallDraw.ts) so the
 * two views never visually drift apart.
 *
 * No coherent-group / Δφ-Δτ column here: today's Allocation model doesn't
 * carry them (tracked as a backend follow-up, not faked).
 */
export function ReplayChannelTile({
  plan,
  deviceId,
  channelIndex,
  runElapsedSeconds,
  catalogue,
  lease,
  nowMs,
}: {
  plan: ReplayPlan;
  deviceId: string;
  channelIndex: number;
  runElapsedSeconds: number;
  catalogue: IQRecording[];
  lease: DeviceLease | undefined;
  nowMs: number;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const active = activeWindowAt(plan, deviceId, channelIndex, runElapsedSeconds);
  const primary = active?.channels[0] ?? null;
  const recording = primary
    ? catalogue.find(
        (r) => r.id === primary.recording.recording_id && r.version === primary.recording.version,
      )
    : null;
  const overview = recording?.overview_spectrogram ?? null;

  // The Allocation carries the physical channel's occupied time span, but
  // not each composite channel's own start offset within it — so playhead
  // position within the recording loops on the recording's own duration,
  // a documented simplification until per-channel-within-window start
  // offsets are modelled (see domain/replay.ts:ActiveWindow's docstring).
  let playheadFraction = 0;
  if (active && recording && recording.duration_s > 0) {
    const elapsedInAllocation = runElapsedSeconds - active.allocation.start_seconds;
    playheadFraction = (elapsedInAllocation % recording.duration_s) / recording.duration_s;
  }

  useEffect(() => {
    if (canvasRef.current && overview) {
      drawWaterfall(canvasRef.current, overview, playheadFraction, "#c62828");
    }
  }, [overview, playheadFraction]);

  const leaseSecondsLeft = lease
    ? Math.max(0, (new Date(lease.expires_at).getTime() - nowMs) / 1000)
    : null;

  return (
    <div
      data-testid={`replay-channel-tile-${deviceId}-${channelIndex}`}
      style={{
        border: `1px solid ${colors.border}`,
        borderRadius: 4,
        padding: 8,
        fontFamily: monoFontStack,
        width: CANVAS_WIDTH + 16,
      }}
    >
      <div style={{ fontSize: 12, fontWeight: 700 }}>
        {deviceId} · ch{channelIndex}
      </div>
      {primary ? (
        <div style={{ fontSize: 11, color: colors.textMuted }}>
          {primary.role} — {mhz(primary.center_frequency_hz)} MHz
          {active && active.channels.length > 1 ? ` (+${active.channels.length - 1} more)` : ""}
        </div>
      ) : (
        <div style={{ fontSize: 11, color: colors.textMuted }}>unmapped / idle</div>
      )}
      {overview ? (
        <canvas
          ref={canvasRef}
          width={CANVAS_WIDTH}
          height={CANVAS_HEIGHT}
          style={{
            border: `1px solid ${colors.border}`,
            imageRendering: "pixelated",
            marginTop: 4,
          }}
        />
      ) : (
        <div
          style={{
            width: CANVAS_WIDTH,
            height: CANVAS_HEIGHT,
            marginTop: 4,
            border: `1px solid ${colors.border}`,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            fontSize: 11,
            color: colors.textMuted,
          }}
        >
          no active recording
        </div>
      )}
      <div style={{ fontSize: 11, color: colors.textMuted, marginTop: 4 }}>
        lease {leaseSecondsLeft === null ? "—" : `${Math.floor(leaseSecondsLeft)}s`}
      </div>
    </div>
  );
}
