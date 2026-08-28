import type { Zone, ZoneType } from "../../domain/types";
import { SelectField, TextAreaField, TextField } from "./fields";

const ZONE_TYPES: readonly ZoneType[] = [
  "operational_area",
  "no_transmit",
  "no_fly",
  "restricted",
  "custom",
];

export interface ZoneFormProps {
  zone: Zone;
  onChange: (zone: Zone) => void;
  onDelete: () => void;
}

/**
 * Non-geometry fields only — drawing/editing the polygon itself is a map
 * interaction deferred out of this pass (see the M3 plan's zone-authoring
 * note); the polygon is authored via the "New scenario" area picker or
 * carried over from a cloned/published version.
 */
export function ZoneForm({ zone, onChange, onDelete }: ZoneFormProps) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10, padding: 16 }}>
      <h3 style={{ margin: 0 }}>Zone</h3>
      <SelectField
        label="Type"
        value={zone.zone_type}
        options={ZONE_TYPES}
        onChange={(zone_type) => onChange({ ...zone, zone_type })}
      />
      <TextField
        label="Label"
        value={zone.label ?? ""}
        onChange={(label) => onChange({ ...zone, label: label || null })}
      />
      <TextAreaField
        label="Notes"
        value={zone.notes ?? ""}
        onChange={(notes) => onChange({ ...zone, notes: notes || null })}
      />
      <button type="button" onClick={onDelete} style={{ alignSelf: "flex-start" }}>
        Delete zone
      </button>
    </div>
  );
}
