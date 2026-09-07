import type { TimelineEvent } from "../../domain/types";
import type { Selection } from "../../state/selection";
import { sectionHeadingStyle } from "../../styles/tokens";
import { TimelineEventsListEditor } from "../properties/TimelineEventsListEditor";
import { PlaybackControls } from "./PlaybackControls";
import { ScrubBar } from "./ScrubBar";

/**
 * The shared scrub spine, docked across the full width of the Development
 * page — cross-cutting because timeline events reference either spatial
 * triggers (mission start, waypoint, area entry) or absolute/manual/
 * external/safety events, so they belong to neither the Spatial nor the
 * Signal panel exclusively. Owns nothing itself: play/pause/seek all read
 * and write the single scenarioTimeContext clock both other panels also
 * read from (rule 14 — one clock, no independent cursors).
 */
export function TimelinePane({
  events,
  maxSeconds,
  selection,
  onSelect,
}: {
  events: TimelineEvent[];
  maxSeconds: number;
  selection: Selection;
  onSelect: (selection: Selection) => void;
}) {
  return (
    <div style={{ display: "flex", flexDirection: "column" }}>
      <div style={{ display: "flex", alignItems: "center" }}>
        <PlaybackControls />
        <div style={{ flex: 1 }}>
          <ScrubBar maxSeconds={maxSeconds} />
        </div>
      </div>
      <div style={{ ...sectionHeadingStyle, padding: "4px 12px 0" }}>Timeline events</div>
      <TimelineEventsListEditor events={events} selection={selection} onSelect={onSelect} />
    </div>
  );
}
