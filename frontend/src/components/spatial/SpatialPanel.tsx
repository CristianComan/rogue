import { useState } from "react";
import type { ScenarioContent } from "../../domain/types";
import type { Selection } from "../../state/selection";
import { Card } from "../shell/Card";
import { MissionsListEditor } from "../properties/MissionsListEditor";
import { ReceiversListEditor } from "../properties/ReceiversListEditor";
import { ZonesListEditor } from "../properties/ZonesListEditor";
import { DopplerBlade } from "./DopplerBlade";

/**
 * "Where things are and how they move" — zones, missions/waypoints and
 * receiver positions grouped under one heading, with a button into the
 * Doppler geometry sub-view (now a wide inspector blade — see
 * DopplerBlade.tsx — rather than an in-panel tab, matching the design
 * canvas's own "click a tile -> inspector blade" pattern). Previously these
 * three lists sat in a flat, unlabeled stack alongside timeline events (an
 * unrelated, cross-cutting concern) with no grouping at all.
 */
export function SpatialPanel({
  content,
  scenarioTimeSeconds,
  maxSeconds,
  selection,
  onSelect,
}: {
  content: ScenarioContent;
  scenarioTimeSeconds: number;
  maxSeconds: number;
  selection: Selection;
  onSelect: (selection: Selection) => void;
}) {
  const [dopplerOpen, setDopplerOpen] = useState(false);

  return (
    <Card
      style={{ height: "100%" }}
      bodyStyle={{ overflowY: "auto" }}
      noPadding
      header={
        <>
          <div
            style={{
              font: "600 11px/1.2 var(--mono)",
              letterSpacing: "0.09em",
              textTransform: "uppercase",
              color: "var(--ink-3)",
            }}
          >
            Spatial Knowledge
          </div>
          <div style={{ marginLeft: "auto" }}>
            <button
              type="button"
              onClick={() => setDopplerOpen(true)}
              style={{
                height: 22,
                padding: "0 7px",
                background: "var(--surface)",
                border: "1px solid var(--line-2)",
                borderRadius: 2,
                cursor: "pointer",
                color: "var(--ink-2)",
                fontSize: 11,
              }}
            >
              Doppler ▸
            </button>
          </div>
        </>
      }
    >
      <div style={{ borderBottom: "1px solid var(--line)" }}>
        <ZonesListEditor zones={content.zones} selection={selection} onSelect={onSelect} />
      </div>
      <div style={{ borderBottom: "1px solid var(--line)" }}>
        <MissionsListEditor missions={content.missions} selection={selection} onSelect={onSelect} />
      </div>
      <div>
        <ReceiversListEditor
          receivers={content.receivers}
          selection={selection}
          onSelect={onSelect}
        />
      </div>
      {dopplerOpen && (
        <DopplerBlade
          receivers={content.receivers}
          missions={content.missions}
          scenarioTimeSeconds={scenarioTimeSeconds}
          maxSeconds={maxSeconds}
          onClose={() => setDopplerOpen(false)}
        />
      )}
    </Card>
  );
}
