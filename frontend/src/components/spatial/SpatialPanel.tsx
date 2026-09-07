import { useState, type ReactNode } from "react";
import type { ScenarioContent } from "../../domain/types";
import type { Selection } from "../../state/selection";
import { colors, sectionHeadingStyle } from "../../styles/tokens";
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
    <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      <div style={{ display: "flex", alignItems: "center", padding: "8px 12px 0" }}>
        <div style={sectionHeadingStyle}>Spatial Knowledge</div>
        <div style={{ marginLeft: "auto", display: "flex", gap: 4 }}>
          <TabButton active={tab === "objects"} onClick={() => setTab("objects")}>
            Objects
          </TabButton>
          <TabButton active={tab === "doppler"} onClick={() => setTab("doppler")}>
            Doppler
          </TabButton>
        </div>
      </div>
      <div style={{ flex: 1, overflowY: "auto" }}>
        {tab === "objects" ? (
          <>
            <div style={{ borderBottom: `1px solid ${colors.borderLight}` }}>
              <ZonesListEditor zones={content.zones} selection={selection} onSelect={onSelect} />
            </div>
            <div style={{ borderBottom: `1px solid ${colors.borderLight}` }}>
              <MissionsListEditor
                missions={content.missions}
                selection={selection}
                onSelect={onSelect}
              />
            </div>
            <div style={{ borderBottom: `1px solid ${colors.borderLight}` }}>
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
      </div>
    </div>
  );
}

function TabButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      style={{
        fontSize: 11,
        padding: "2px 8px",
        border: `1px solid ${colors.border}`,
        background: active ? colors.selectedBg : "transparent",
        cursor: "pointer",
      }}
    >
      {children}
    </button>
  );
}
