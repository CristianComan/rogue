import { SpectrumStrip } from "../timeline/SpectrumStrip";
import { Waterfall } from "../timeline/Waterfall";
import type { DroneMission, IQRecording } from "../../domain/types";
import type { Selection } from "../../state/selection";
import { sectionHeadingStyle } from "../../styles/tokens";
import { SignalLinksListEditor } from "./SignalLinksListEditor";

/**
 * "What transmits and when" — every RF link across the scenario, the
 * authored-intent spectrum preview and per-link waterfalls, all in one
 * dedicated full-width area. Previously this content was split: links only
 * reachable by first selecting a mission, waterfalls buried inside
 * TimelinePane alongside playback controls that belong to the (shared)
 * Timeline strip instead.
 */
export function SignalPanel({
  missions,
  scenarioTimeSeconds,
  selection,
  onSelect,
  catalogue,
}: {
  missions: DroneMission[];
  scenarioTimeSeconds: number;
  selection: Selection;
  onSelect: (selection: Selection) => void;
  catalogue: IQRecording[];
}) {
  return (
    <div style={{ display: "flex", flexDirection: "column" }}>
      <div style={{ ...sectionHeadingStyle, padding: "8px 12px 4px" }}>Signal Knowledge</div>
      <SignalLinksListEditor
        missions={missions}
        scenarioTimeSeconds={scenarioTimeSeconds}
        selection={selection}
        onSelect={onSelect}
      />
      <SpectrumStrip missions={missions} />
      <div style={{ display: "flex", flexWrap: "wrap" }}>
        {missions.flatMap((mission) =>
          mission.rf_links.map((link) => (
            <Waterfall key={link.id} link={link} missionName={mission.name} catalogue={catalogue} />
          )),
        )}
      </div>
    </div>
  );
}
