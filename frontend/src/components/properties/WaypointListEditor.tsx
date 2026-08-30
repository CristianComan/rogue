import type { AltitudeReference, Waypoint } from "../../domain/types";
import { NumberField, SelectField } from "./fields";

const ALTITUDE_REFERENCES: readonly AltitudeReference[] = ["agl", "msl"];

export interface WaypointListEditorProps {
  waypoints: Waypoint[];
  onChange: (waypoints: Waypoint[]) => void;
}

function renumbered(waypoints: Waypoint[]): Waypoint[] {
  return waypoints.map((w, i) => ({ ...w, sequence_index: i }));
}

export function WaypointListEditor({ waypoints, onChange }: WaypointListEditorProps) {
  const ordered = [...waypoints].sort((a, b) => a.sequence_index - b.sequence_index);

  function updateAt(index: number, patch: Partial<Waypoint>) {
    const next = ordered.map((w, i) => (i === index ? { ...w, ...patch } : w));
    onChange(next);
  }

  function removeAt(index: number) {
    onChange(renumbered(ordered.filter((_, i) => i !== index)));
  }

  function move(index: number, direction: -1 | 1) {
    const target = index + direction;
    if (target < 0 || target >= ordered.length) return;
    const next = [...ordered];
    [next[index], next[target]] = [next[target], next[index]];
    onChange(renumbered(next));
  }

  function addWaypoint() {
    const last = ordered[ordered.length - 1];
    const newWaypoint: Waypoint = {
      sequence_index: ordered.length,
      position: { type: "Point", coordinates: last ? last.position.coordinates : [0, 0] },
      altitude_m: last?.altitude_m ?? 100,
      altitude_reference: last?.altitude_reference ?? "agl",
      speed_mps: null,
      heading_deg: null,
      hold_seconds: 0,
    };
    onChange([...ordered, newWaypoint]);
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      {ordered.map((w, i) => (
        <div
          key={i}
          data-testid={`waypoint-row-${i}`}
          style={{
            border: "1px solid #ccc",
            padding: 8,
            display: "flex",
            flexDirection: "column",
            gap: 6,
          }}
        >
          <strong>Waypoint {i}</strong>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <NumberField
              label="Lon"
              value={w.position.coordinates[0]}
              step={0.0001}
              onChange={(lon) =>
                updateAt(i, {
                  position: { type: "Point", coordinates: [lon, w.position.coordinates[1]] },
                })
              }
            />
            <NumberField
              label="Lat"
              value={w.position.coordinates[1]}
              step={0.0001}
              onChange={(lat) =>
                updateAt(i, {
                  position: { type: "Point", coordinates: [w.position.coordinates[0], lat] },
                })
              }
            />
          </div>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <NumberField
              label="Altitude (m)"
              value={w.altitude_m}
              onChange={(altitude_m) => updateAt(i, { altitude_m })}
            />
            <SelectField
              label="Reference"
              value={w.altitude_reference}
              options={ALTITUDE_REFERENCES}
              onChange={(altitude_reference) => updateAt(i, { altitude_reference })}
            />
          </div>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <NumberField
              label="Speed override (m/s)"
              value={w.speed_mps ?? 0}
              onChange={(v) => updateAt(i, { speed_mps: v || null })}
            />
            <NumberField
              label="Hold (s)"
              value={w.hold_seconds}
              onChange={(hold_seconds) => updateAt(i, { hold_seconds })}
            />
          </div>
          <div style={{ display: "flex", gap: 6 }}>
            <button type="button" onClick={() => move(i, -1)} disabled={i === 0}>
              ↑
            </button>
            <button type="button" onClick={() => move(i, 1)} disabled={i === ordered.length - 1}>
              ↓
            </button>
            <button type="button" onClick={() => removeAt(i)} disabled={ordered.length <= 2}>
              Remove
            </button>
          </div>
        </div>
      ))}
      <button type="button" onClick={addWaypoint} style={{ alignSelf: "flex-start" }}>
        + Waypoint
      </button>
    </div>
  );
}
