import { physicalChannelsInPlan, type ReplayPlan } from "../../domain/replay";
import { useRunTime } from "../../state/runTimeContext";
import type { DroneMission, IQRecording } from "../../domain/types";
import { Badge } from "../shell/Badge";
import { ReplayChannelTile } from "./ReplayChannelTile";

const RUNNING_STATUSES = new Set(["running"]);

/**
 * A tile grid, one per physical TX channel the compiled plan allocates —
 * the Replay page's counterpart to the Development page's per-link
 * waterfalls (SignalPanel). "Physical channel" here, not "logical link",
 * is the point: this shows what actually keyed on real (or simulated)
 * hardware, not authored intent. The legend above it states the real
 * allocation rules a channel's badge follows (ADR-003/ADR-012) so a
 * DETECT vs CG-xxxx badge doesn't need explaining per-tile.
 */
export function ChannelWaterfallGrid({
  plan,
  catalogue,
  missions,
}: {
  plan: ReplayPlan;
  catalogue: IQRecording[];
  missions: DroneMission[];
}) {
  const { run, runElapsedSeconds, nowMs } = useRunTime();
  const channels = physicalChannelsInPlan(plan);
  const runRunning = RUNNING_STATUSES.has(run.status);

  return (
    <div>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 12,
          padding: "8px 12px",
          borderBottom: "1px solid var(--line)",
        }}
      >
        <div style={{ font: "600 11px/1 var(--mono)", letterSpacing: "0.04em" }}>
          RF spectrum — {channels.length} physical channel{channels.length === 1 ? "" : "s"}
        </div>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 10,
            flexWrap: "wrap",
            fontSize: 10.5,
            color: "var(--ink-3)",
          }}
        >
          <span>DETECT — one drone signal per channel</span>
          <span>·</span>
          <span>CG-xxxx — parallel coherent channels, one drone, combined on the RF network</span>
          <span>·</span>
          <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
            <Badge tone="mute">PLANNED</Badge>
            digital-domain combining, several drones per channel
          </span>
        </div>
      </div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, padding: 12 }}>
        {channels.map(({ device_id, channel_index }) => (
          <ReplayChannelTile
            key={`${device_id}:${channel_index}`}
            plan={plan}
            deviceId={device_id}
            channelIndex={channel_index}
            runElapsedSeconds={runElapsedSeconds}
            catalogue={catalogue}
            missions={missions}
            nowMs={nowMs}
            runRunning={runRunning}
            lease={run.device_leases.find(
              (l) => l.device_id === device_id && l.channel_index === channel_index,
            )}
          />
        ))}
      </div>
    </div>
  );
}
