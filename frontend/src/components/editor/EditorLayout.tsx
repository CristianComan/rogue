import { useEffect, useState } from "react";
import type { Dispatch, ReactNode } from "react";
import { listRecordings } from "../../api/recordings";
import { MapCanvas } from "../map/MapCanvas";
import { Card } from "../shell/Card";
import { PropertiesPane } from "../properties/PropertiesPane";
import { SignalPanel } from "../signal/SignalPanel";
import { SpatialPanel } from "../spatial/SpatialPanel";
import { TimelinePane } from "../timeline/TimelinePane";
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
        <div
          style={{
            borderBottom: "1px solid var(--border-default)",
            background: "var(--surface-card)",
            padding: "10px 20px",
          }}
        >
          {toolbar}
        </div>
      )}
      <div
        style={{
          flex: "1 1 55%",
          display: "flex",
          gap: "var(--space-2)",
          minHeight: 0,
          padding: "var(--space-2)",
        }}
      >
        <div style={{ flex: "1 1 60%", minWidth: 0 }}>
          <Card noPadding style={{ height: "100%" }}>
            <MapCanvas
              zones={content.zones}
              missions={content.missions}
              receivers={content.receivers}
              scenarioTimeSeconds={scenarioTimeSeconds}
              selection={selection}
              onSelect={select}
            />
          </Card>
        </div>
        <div
          style={{
            flex: "0 0 360px",
            display: "flex",
            flexDirection: "column",
            gap: "var(--space-2)",
            minHeight: 0,
          }}
        >
          <div style={{ flex: "1 1 auto", minHeight: 0 }}>
            <SpatialPanel
              content={content}
              scenarioTimeSeconds={scenarioTimeSeconds}
              selection={selection}
              onSelect={select}
            />
          </div>
          <div style={{ flex: "0 0 auto", maxHeight: "42%", overflowY: "auto" }}>
            <Card noPadding>
              <PropertiesPane
                content={content}
                selection={selection}
                dispatch={dispatch}
                onClearSelection={() => select(null)}
                catalogue={catalogue}
              />
            </Card>
          </div>
        </div>
      </div>
      <div style={{ flex: "1 1 30%", minHeight: 0, padding: "0 var(--space-2) var(--space-2)" }}>
        <SignalPanel
          missions={content.missions}
          maxSeconds={maxSeconds}
          selection={selection}
          onSelect={select}
          catalogue={catalogue}
        />
      </div>
      <div style={{ flex: "0 0 auto", padding: "0 var(--space-2) var(--space-2)" }}>
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
