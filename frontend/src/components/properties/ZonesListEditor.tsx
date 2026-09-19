import type { Zone } from "../../domain/types";
import type { Selection } from "../../state/selection";

export interface ZonesListEditorProps {
  zones: Zone[];
  selection: Selection;
  onSelect: (selection: Selection) => void;
}

/**
 * An always-visible list of the scenario's zones, next to
 * RecordingsListEditor — zones otherwise only exist as map-clickable
 * polygons, so one positioned outside whatever the map currently happens to
 * be showing is invisible and effectively unreachable. Not an inline editor
 * like RecordingsListEditor: zones already have real create (toolbar)/
 * select (map or here)/edit (ZoneForm, via selection)/delete
 * (ZoneForm) — this only adds the missing "see everything" affordance.
 */
export function ZonesListEditor({ zones, selection, onSelect }: ZonesListEditorProps) {
  return (
    <div
      data-testid="zones-panel"
      style={{ display: "flex", flexDirection: "column", gap: 4, padding: 12 }}
    >
      <strong style={{ fontSize: 12 }}>Zones</strong>
      {zones.length === 0 && (
        <span style={{ fontSize: 12, color: "#4c5c5e" }}>No zones in this scenario.</span>
      )}
      {zones.map((zone) => {
        const isSelected = selection?.kind === "zone" && selection.id === zone.id;
        return (
          <button
            key={zone.id}
            type="button"
            data-testid={`zones-panel-row-${zone.id}`}
            onClick={() => onSelect({ kind: "zone", id: zone.id })}
            style={{
              textAlign: "left",
              fontSize: 12,
              padding: "4px 6px",
              background: isSelected ? "#e4ebe8" : "transparent",
              border: "1px solid #ccc",
              cursor: "pointer",
            }}
          >
            {zone.label || "(unlabeled zone)"} · {zone.zone_type}
          </button>
        );
      })}
    </div>
  );
}
