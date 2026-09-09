import { useState } from "react";
import type { ScenarioContent } from "../../domain/types";
import type { Selection } from "../../state/selection";
import { Card } from "../shell/Card";
import { MissionsListEditor } from "../properties/MissionsListEditor";
import { ReceiversListEditor } from "../properties/ReceiversListEditor";
import { ZonesListEditor } from "../properties/ZonesListEditor";
import { DopplerView } from "./DopplerView";

type SpatialTab = "objects" | "doppler";

/**
 * "Where things are and how they move" — zones, missions/waypoints and
 * receiver positions grouped under one heading, with a toggle into the
 * Doppler geometry sub-view. Previously these three lists sat in a flat,
 * unlabeled stack alongside timeline events (an unrelated, cross-cutting
 * concern) with no grouping at all.
 */
export function SpatialPanel({
  content,
  scenarioTimeSeconds,
  selection,
  onSelect,
}: {
  content: ScenarioContent;
  scenarioTimeSeconds: number;
  selection: Selection;
  onSelect: (selection: Selection) => void;
}) {
  const [tab, setTab] = useState<SpatialTab>("objects");

  return (
    <Card
      style={{ height: "100%" }}
      bodyStyle={{ overflowY: "auto" }}
      noPadding
      header={
        <>
          <div
            style={{
              fontSize: 11,
              fontWeight: 600,
              letterSpacing: "0.06em",
              textTransform: "uppercase",
              color: "var(--text-secondary)",
            }}
          >
            Spatial Knowledge
          </div>
          <div style={{ marginLeft: "auto", display: "flex", gap: 4 }}>
            <TabButton active={tab === "objects"} onClick={() => setTab("objects")}>
              Objects
            </TabButton>
            <TabButton active={tab === "doppler"} onClick={() => setTab("doppler")}>
              Doppler
            </TabButton>
          </div>
        </>
      }
    >
      {tab === "objects" ? (
        <>
          <div style={{ borderBottom: "1px solid var(--border-subtle)" }}>
            <ZonesListEditor zones={content.zones} selection={selection} onSelect={onSelect} />
          </div>
          <div style={{ borderBottom: "1px solid var(--border-subtle)" }}>
            <MissionsListEditor
              missions={content.missions}
              selection={selection}
              onSelect={onSelect}
            />
          </div>
          <div>
            <ReceiversListEditor
              receivers={content.receivers}
              selection={selection}
              onSelect={onSelect}
            />
          </div>
        </>
      ) : (
        <DopplerView
          receivers={content.receivers}
          missions={content.missions}
          scenarioTimeSeconds={scenarioTimeSeconds}
        />
      )}
    </Card>
  );
}

function TabButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      style={{
        fontSize: 11,
        padding: "2px 8px",
        border: "1px solid var(--border-default)",
        background: active ? "var(--surface-selected)" : "var(--surface-card)",
      }}
    >
      {children}
    </button>
  );
}
