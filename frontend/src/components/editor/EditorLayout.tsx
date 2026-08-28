import type { Dispatch, ReactNode } from "react";
import { MapCanvas } from "../map/MapCanvas";
import { PropertiesPane } from "../properties/PropertiesPane";
import { RecordingsListEditor } from "../properties/RecordingsListEditor";
import type { ScenarioContent } from "../../domain/types";
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
            display: "flex",
            flexDirection: "column",
          }}
        >
          <div style={{ borderBottom: "1px solid #eee" }}>
            <RecordingsListEditor
              recordings={content.recordings}
              onChange={(recordings) => dispatch({ type: "setRecordings", recordings })}
            />
          </div>
          <PropertiesPane
            content={content}
            selection={selection}
            dispatch={dispatch}
            onClearSelection={() => select(null)}
          />
        </div>
      </div>
      {timeline && <div style={{ borderTop: "1px solid #ccc", flex: "0 0 auto" }}>{timeline}</div>}
    </div>
  );
}
