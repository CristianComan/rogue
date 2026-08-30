import type { DroneMission } from "../../domain/types";
import type { Selection } from "../../state/selection";

export interface MissionsListEditorProps {
  missions: DroneMission[];
  selection: Selection;
  onSelect: (selection: Selection) => void;
}

/**
 * An always-visible list of the scenario's missions, alongside
 * ZonesListEditor/RecordingsListEditor — a mission otherwise only exists as
 * a map-clickable drone track, so one off-screen or overlapping another is
 * hard to reach. Not an inline editor: missions already have real create
 * (toolbar)/select (map or here)/edit (MissionForm)/delete (MissionForm) —
 * this only adds the missing "see everything" affordance.
 */
export function MissionsListEditor({ missions, selection, onSelect }: MissionsListEditorProps) {
  return (
    <div
      data-testid="missions-panel"
      style={{ display: "flex", flexDirection: "column", gap: 4, padding: 12 }}
    >
      <strong style={{ fontSize: 12 }}>Missions</strong>
      {missions.length === 0 && (
        <span style={{ fontSize: 12, color: "#4c5c5e" }}>No missions in this scenario.</span>
      )}
      {missions.map((mission) => {
        const isSelected = selection?.kind === "mission" && selection.id === mission.id;
        return (
          <button
            key={mission.id}
            type="button"
            data-testid={`missions-panel-row-${mission.id}`}
            onClick={() => onSelect({ kind: "mission", id: mission.id })}
            style={{
              textAlign: "left",
              fontSize: 12,
              padding: "4px 6px",
              background: isSelected ? "#e4ebe8" : "transparent",
              border: "1px solid #ccc",
              cursor: "pointer",
            }}
          >
            {mission.name} · {mission.platform.category}
            {mission.rf_links.length > 0 ? ` · ${mission.rf_links.length} RF link(s)` : ""}
          </button>
        );
      })}
    </div>
  );
}
