import { useEffect, useState } from "react";
import type { Dispatch, ReactNode } from "react";
import { listRecordings } from "../../api/recordings";
import { MapCanvas } from "../map/MapCanvas";
import { MissionsListEditor } from "../properties/MissionsListEditor";
import { PropertiesPane } from "../properties/PropertiesPane";
import { ReceiversListEditor } from "../properties/ReceiversListEditor";
import { TimelineEventsListEditor } from "../properties/TimelineEventsListEditor";
import { ZonesListEditor } from "../properties/ZonesListEditor";
import type { IQRecording, ScenarioContent } from "../../domain/types";
import type { EditorAction } from "../../state/editorReducer";
import { useSelection } from "../../state/selectionContext";

export interface EditorLayoutProps {
  content: ScenarioContent;
  scenarioTimeSeconds: number;
  dispatch: Dispatch<EditorAction>;
  toolbar?: ReactNode;
  timeline?: ReactNode;
}

/**
 * Three-pane desktop layout per system-design.md §5: map, selected-object
 * properties, timeline/resources. Selection is the single source of truth
 * shared by the map and the properties pane (state/selectionContext.tsx).
 */
export function EditorLayout({
  content,
  scenarioTimeSeconds,
  dispatch,
  toolbar,
  timeline,
}: EditorLayoutProps) {
  const { selection, select } = useSelection();
  // Fetched once here (not per-form) and passed down to whichever form
  // needs to resolve/pick a recording — via PropertiesPane -> MissionForm ->
  // RfLinkForm, each emission's picker.
  const [catalogue, setCatalogue] = useState<IQRecording[]>([]);

  useEffect(() => {
    let cancelled = false;
    listRecordings({ limit: 200 })
      .then((recordings) => {
        if (!cancelled) setCatalogue(recordings);
      })
      .catch(() => {
        // The pickers fall back to plain text entry when the catalogue is
        // empty/unreachable — not fatal to the editor.
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      {toolbar && <div style={{ borderBottom: "1px solid #ccc", padding: 8 }}>{toolbar}</div>}
      <div style={{ flex: 1, display: "flex", minHeight: 0 }}>
        <div style={{ flex: "1 1 60%", minWidth: 0 }}>
          <MapCanvas
            zones={content.zones}
            missions={content.missions}
            receivers={content.receivers}
            scenarioTimeSeconds={scenarioTimeSeconds}
            selection={selection}
            onSelect={select}
          />
        </div>
        <div
          style={{
            flex: "0 0 340px",
            borderLeft: "1px solid #ccc",
            overflowY: "auto",
            overflowX: "auto",
            display: "flex",
            flexDirection: "column",
          }}
        >
          <div style={{ borderBottom: "1px solid #eee" }}>
            <ZonesListEditor zones={content.zones} selection={selection} onSelect={select} />
          </div>
          <div style={{ borderBottom: "1px solid #eee" }}>
            <MissionsListEditor
              missions={content.missions}
              selection={selection}
              onSelect={select}
            />
          </div>
          <div style={{ borderBottom: "1px solid #eee" }}>
            <ReceiversListEditor
              receivers={content.receivers}
              selection={selection}
              onSelect={select}
            />
          </div>
          <div style={{ borderBottom: "1px solid #eee" }}>
            <TimelineEventsListEditor
              events={content.timeline_events}
              selection={selection}
              onSelect={select}
            />
          </div>
          <PropertiesPane
            content={content}
            selection={selection}
            dispatch={dispatch}
            onClearSelection={() => select(null)}
            catalogue={catalogue}
          />
        </div>
      </div>
      {timeline && <div style={{ borderTop: "1px solid #ccc", flex: "0 0 auto" }}>{timeline}</div>}
    </div>
  );
}
