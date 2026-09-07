import { physicalChannelsInPlan, type ReplayPlan } from "../../domain/replay";
import { useRunTime } from "../../state/runTimeContext";
import type { IQRecording } from "../../domain/types";
import { sectionHeadingStyle } from "../../styles/tokens";
import { ReplayChannelTile } from "./ReplayChannelTile";

/**
 * A tile grid, one per physical TX channel the compiled plan allocates —
 * the Replay page's counterpart to the Development page's per-link
 * waterfalls (SignalPanel). "Physical channel" here, not "logical link",
 * is the point: this shows what actually keyed on real (or simulated)
 * hardware, not authored intent.
 */
export function ChannelWaterfallGrid({
  plan,
  catalogue,
}: {
  plan: ReplayPlan;
  catalogue: IQRecording[];
}) {
  const { run, runElapsedSeconds, nowMs } = useRunTime();
  const channels = physicalChannelsInPlan(plan);

  return (
    <div>
      <div style={{ ...sectionHeadingStyle, padding: "8px 12px 4px" }}>
        RF spectrum — {channels.length} physical channel{channels.length === 1 ? "" : "s"}
      </div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, padding: "0 12px 12px" }}>
        {channels.map(({ device_id, channel_index }) => (
          <ReplayChannelTile
            key={`${device_id}:${channel_index}`}
            plan={plan}
            deviceId={device_id}
            channelIndex={channel_index}
            runElapsedSeconds={runElapsedSeconds}
            catalogue={catalogue}
            nowMs={nowMs}
            lease={run.device_leases.find(
              (l) => l.device_id === device_id && l.channel_index === channel_index,
            )}
          />
        ))}
      </div>
    </div>
  );
}
