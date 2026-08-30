import { useEffect, useState } from "react";
import { listRecordings } from "../../api/recordings";
import type { DroneMission, IQRecording } from "../../domain/types";
import { PlaybackControls } from "./PlaybackControls";
import { ScrubBar } from "./ScrubBar";
import { SpectrumStrip } from "./SpectrumStrip";
import { Waterfall } from "./Waterfall";

export function TimelinePane({
  missions,
  maxSeconds,
}: {
  missions: DroneMission[];
  maxSeconds: number;
}) {
  // Fetched independently of EditorLayout's own catalogue fetch — TimelinePane
  // is handed to EditorLayout as a pre-built ReactNode (see
  // routes/ScenarioEditorPage.tsx), before EditorLayout's catalogue state
  // exists, so there's no prop path to share that fetch without a larger
  // restructuring of that composition. A small duplicate GET /recordings
  // call, not a correctness issue.
  const [catalogue, setCatalogue] = useState<IQRecording[]>([]);

  useEffect(() => {
    let cancelled = false;
    listRecordings({ limit: 200 })
      .then((recordings) => {
        if (!cancelled) setCatalogue(recordings);
      })
      .catch(() => {
        // Waterfall treats an unresolved duration conservatively; not fatal.
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div style={{ display: "flex", flexDirection: "column" }}>
      <div style={{ display: "flex", alignItems: "center" }}>
        <PlaybackControls />
        <div style={{ flex: 1 }}>
          <ScrubBar maxSeconds={maxSeconds} />
        </div>
      </div>
      <SpectrumStrip missions={missions} />
      {missions.flatMap((mission) =>
        mission.rf_links.map((link) => (
          <Waterfall key={link.id} link={link} missionName={mission.name} catalogue={catalogue} />
        )),
      )}
    </div>
  );
}
