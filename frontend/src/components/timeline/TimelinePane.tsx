import type { DroneMission } from "../../domain/types";
import { PlaybackControls } from "./PlaybackControls";
import { ScrubBar } from "./ScrubBar";
import { SpectrumStrip } from "./SpectrumStrip";

export function TimelinePane({
  missions,
  maxSeconds,
}: {
  missions: DroneMission[];
  maxSeconds: number;
}) {
  return (
    <div style={{ display: "flex", flexDirection: "column" }}>
      <div style={{ display: "flex", alignItems: "center" }}>
        <PlaybackControls />
        <div style={{ flex: 1 }}>
          <ScrubBar maxSeconds={maxSeconds} />
        </div>
      </div>
      <SpectrumStrip missions={missions} />
    </div>
  );
}
