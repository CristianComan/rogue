import { useEffect, useRef } from "react";
import { activeWindowAt, type ReplayPlan } from "../../domain/replay";
import type { DeviceLease } from "../../domain/run";
import type { DroneMission, IQRecording } from "../../domain/types";
import { toneVars, type Tone } from "../../styles/tokens";
import { drawWaterfall } from "../timeline/waterfallDraw";

const CANVAS_WIDTH = 246;
const CANVAS_HEIGHT = 96;

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
 * No per-channel power (dBFS) column here — that's not modelled anywhere
 * real yet, so it's left out rather than invented; the coherent-group
 * badge *is* real (ADR-012), shown whenever the active allocation actually
 * carries a `coherent_group_id`.
 */
export function ReplayChannelTile({
  plan,
  deviceId,
  channelIndex,
  runElapsedSeconds,
  catalogue,
  missions,
  lease,
  nowMs,
  runRunning,
}: {
  plan: ReplayPlan;
  deviceId: string;
  channelIndex: number;
  runElapsedSeconds: number;
  catalogue: IQRecording[];
  missions: DroneMission[];
  lease: DeviceLease | undefined;
  nowMs: number;
  runRunning: boolean;
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
  const missionName = primary ? missions.find((m) => m.id === primary.mission_id)?.name : undefined;

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
      drawWaterfall(canvasRef.current, overview, playheadFraction, "#e0524a");
    }
  }, [overview, playheadFraction]);

  const leaseSecondsLeft = lease
    ? Math.max(0, (new Date(lease.expires_at).getTime() - nowMs) / 1000)
    : null;

  let state: string;
  let stateTone: Tone;
  if (primary && runRunning) {
    state = "TX";
    stateTone = "ok";
  } else if (primary) {
    state = "ARMED";
    stateTone = "warn";
  } else if (lease) {
    state = "RESERVED";
    stateTone = "mute";
  } else {
    state = "IDLE";
    stateTone = "mute";
  }
  const stateVars = toneVars(stateTone);

  const groupTone: Tone = primary?.coherent_group_id ? "info" : "mute";
  const groupVars = toneVars(groupTone);
  const groupLabel = primary?.coherent_group_id
    ? `CG-${primary.coherent_group_id.slice(0, 4)}`
    : "DETECT";

  return (
    <div
      data-testid={`replay-channel-tile-${deviceId}-${channelIndex}`}
      style={{
        border: "1px solid var(--line)",
        borderRadius: 3,
        background: "var(--surface)",
        overflow: "hidden",
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 6,
          padding: "6px 9px",
          borderBottom: "1px solid var(--line)",
          background: "var(--surface-2)",
        }}
      >
        <span style={{ display: "flex", alignItems: "center", gap: 7, minWidth: 0 }}>
          <span style={{ font: "600 11.5px/1 var(--mono)" }}>
            {deviceId} · ch{channelIndex}
          </span>
          <span
            style={{
              font: "500 9.5px/1.7 var(--mono)",
              padding: "0 5px",
              borderRadius: 2,
              whiteSpace: "nowrap",
              color: groupVars.fg,
              background: groupVars.bg,
              border: `1px solid ${groupVars.bd}`,
            }}
          >
            {groupLabel}
          </span>
        </span>
        <span
          style={{
            display: "inline-flex",
            alignItems: "center",
            padding: "0 6px",
            borderRadius: 10,
            font: "500 10px/1.7 var(--mono)",
            color: stateVars.fg,
            background: stateVars.bg,
            border: `1px solid ${stateVars.bd}`,
          }}
        >
          {state}
        </span>
      </div>

      <div
        style={{
          position: "relative",
          height: CANVAS_HEIGHT,
          background: "var(--wf)",
          overflow: "hidden",
        }}
      >
        {overview ? (
          <canvas
            ref={canvasRef}
            width={CANVAS_WIDTH}
            height={CANVAS_HEIGHT}
            style={{ width: "100%", height: "100%", imageRendering: "pixelated", display: "block" }}
          />
        ) : (
          <div
            style={{
              width: "100%",
              height: "100%",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              font: "400 11px/1 var(--mono)",
              color: "rgba(255,255,255,.4)",
            }}
          >
            {primary ? "no spectrogram overview" : "unmapped / idle"}
          </div>
        )}
        {overview && state === "TX" && (
          <div
            aria-hidden
            style={{
              position: "absolute",
              left: 0,
              right: 0,
              height: 12,
              background: "linear-gradient(rgba(255,255,255,.10),transparent)",
              animation: "wfscan 5.5s linear infinite",
            }}
          />
        )}
        {primary && (
          <div
            style={{
              position: "absolute",
              left: 7,
              bottom: 5,
              font: "500 10px/1 var(--mono)",
              color: "rgba(255,255,255,.72)",
            }}
          >
            {mhz(primary.center_frequency_hz)} MHz
          </div>
        )}
        {primary && (
          <div
            style={{
              position: "absolute",
              right: 7,
              bottom: 5,
              font: "400 9.5px/1 var(--mono)",
              color: "rgba(255,255,255,.45)",
            }}
          >
            {(primary.bandwidth_hz / 1e6).toFixed(1)} MHz
          </div>
        )}
      </div>

      <div style={{ padding: "7px 9px", display: "flex", flexDirection: "column", gap: 2 }}>
        <div style={{ font: "400 11px/1.5 var(--mono)", color: "var(--ink-2)" }}>{deviceId}</div>
        {primary ? (
          <div
            style={{
              fontSize: 11.5,
              minWidth: 0,
              whiteSpace: "nowrap",
              overflow: "hidden",
              textOverflow: "ellipsis",
            }}
          >
            {primary.role.toUpperCase()} — {missionName ?? primary.mission_id.slice(0, 8)}
            {active && active.channels.length > 1 ? ` (+${active.channels.length - 1} more)` : ""}
          </div>
        ) : (
          <div style={{ fontSize: 11.5, color: "var(--ink-3)" }}>unmapped — spare allocation</div>
        )}
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            font: "400 10.5px/1.4 var(--mono)",
            color: "var(--ink-3)",
          }}
        >
          <span>lease {leaseSecondsLeft === null ? "—" : `${Math.floor(leaseSecondsLeft)}s`}</span>
          <span>
            {primary?.delay_offset_s ? `τ ${(primary.delay_offset_s * 1e9).toFixed(0)} ns` : ""}
          </span>
        </div>
      </div>
    </div>
  );
}
