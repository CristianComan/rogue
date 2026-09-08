import { useEffect, useState } from "react";
import type { Dispatch, ReactNode } from "react";
import { listRecordings } from "../../api/recordings";
import { MapCanvas } from "../map/MapCanvas";
import { PropertiesPane } from "../properties/PropertiesPane";
import { SignalPanel } from "../signal/SignalPanel";
import { SpatialPanel } from "../spatial/SpatialPanel";
import { TimelinePane } from "../timeline/TimelinePane";
import { colors } from "../../styles/tokens";
import type { IQRecording, ScenarioContent } from "../../domain/types";
import type { EditorAction } from "../../state/editorReducer";
import { useSelection } from "../../state/selectionContext";

export interface EditorLayoutProps {
  content: ScenarioContent;
  scenarioTimeSeconds: number;
  maxSeconds: number;
  dispatch: Dispatch<EditorAction>;
  toolbar?: ReactNode;
}

/**
 * Three-row layout: Row 1 is the map plus Spatial Knowledge (where things
 * are and how they move — zones/missions/waypoints/receivers, plus the
 * Doppler geometry sub-view); Row 2 is Signal Knowledge, full width (what
 * transmits and when — every RF link across the scenario, spectrum preview,
 * per-link waterfalls); Row 3 is the shared Timeline scrub spine, docked at
 * the bottom, spanning both. Selection is the single source of truth shared
 * by every row (state/selectionContext.tsx); PropertiesPane stays anchored
 * under the map since it already routes every selection kind (zone,
 * mission, waypoint, receiver, rfLink, timelineEvent) to the right form.
 */
export function EditorLayout({
  content,
  scenarioTimeSeconds,
  maxSeconds,
  dispatch,
  toolbar,
}: EditorLayoutProps) {
  const { selection, select } = useSelection();
  // Fetched once here (not per-form) and passed down to whichever form
  // needs to resolve/pick a recording — via PropertiesPane -> MissionForm ->
  // RfLinkForm, each emission's picker, and to SignalPanel's waterfalls.
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
      {toolbar && (
        <div style={{ borderBottom: `1px solid ${colors.border}`, padding: 8 }}>{toolbar}</div>
      )}
      <div style={{ flex: "1 1 55%", display: "flex", minHeight: 0 }}>
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
            borderLeft: `1px solid ${colors.border}`,
            overflowY: "auto",
            overflowX: "auto",
            display: "flex",
            flexDirection: "column",
          }}
        >
          <SpatialPanel
            content={content}
            scenarioTimeSeconds={scenarioTimeSeconds}
            selection={selection}
            onSelect={select}
          />
          <PropertiesPane
            content={content}
            selection={selection}
            dispatch={dispatch}
            onClearSelection={() => select(null)}
            catalogue={catalogue}
          />
        </div>
      </div>
      <div
        style={{
          flex: "1 1 30%",
          minHeight: 0,
          overflowY: "auto",
          borderTop: `1px solid ${colors.border}`,
        }}
      >
        <SignalPanel
          missions={content.missions}
          scenarioTimeSeconds={scenarioTimeSeconds}
          selection={selection}
          onSelect={select}
          catalogue={catalogue}
        />
      </div>
      <div style={{ flex: "0 0 auto", borderTop: `1px solid ${colors.border}` }}>
        <TimelinePane
          events={content.timeline_events}
          maxSeconds={maxSeconds}
          selection={selection}
          onSelect={select}
        />
      </div>
    </div>
  );
}
