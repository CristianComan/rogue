import type { GeoPolygon } from "../../domain/types";
import { NumberField } from "./fields";

export interface ZonePolygonEditorProps {
  polygon: GeoPolygon;
  onChange: (polygon: GeoPolygon) => void;
}

/**
 * Edits a zone's exterior ring only — no holes, matching the "New scenario"
 * area picker's own simplicity (backend/rogue/domain/common.py's GeoPolygon
 * supports interior rings, but authoring one has never had a UI, on the map
 * or here). Mirrors WaypointListEditor's per-point Lon/Lat + add/remove/
 * reorder pattern.
 *
 * GeoPolygon.coordinates[0]'s validator requires a *closed* ring (first
 * point === last point) — this editor only ever shows and edits the
 * non-duplicate vertices, and keeps the closing point in sync automatically
 * so the user can't produce an invalid (open) ring.
 */
export function ZonePolygonEditor({ polygon, onChange }: ZonePolygonEditorProps) {
  const ring = polygon.coordinates[0];
  // The authored vertices, excluding the closing duplicate of the first point.
  const vertices = ring.slice(0, -1);

  function commit(nextVertices: GeoPolygon["coordinates"][number]) {
    const closed = nextVertices.length > 0 ? [...nextVertices, nextVertices[0]] : nextVertices;
    onChange({ ...polygon, coordinates: [closed, ...polygon.coordinates.slice(1)] });
  }

  function updateAt(index: number, lon: number, lat: number) {
    commit(vertices.map((v, i) => (i === index ? [lon, lat] : v)));
  }

  function removeAt(index: number) {
    commit(vertices.filter((_, i) => i !== index));
  }

  function move(index: number, direction: -1 | 1) {
    const target = index + direction;
    if (target < 0 || target >= vertices.length) return;
    const next = [...vertices];
    [next[index], next[target]] = [next[target], next[index]];
    commit(next);
  }

  function addVertex() {
    const last = vertices[vertices.length - 1];
    commit([...vertices, last ? [last[0], last[1]] : [0, 0]]);
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      {vertices.map((v, i) => (
        <div key={i} data-testid={`zone-vertex-${i}`} style={{ display: "flex", gap: 8 }}>
          <NumberField
            label="Lon"
            value={v[0]}
            step={0.0001}
            onChange={(lon) => updateAt(i, lon, v[1])}
          />
          <NumberField
            label="Lat"
            value={v[1]}
            step={0.0001}
            onChange={(lat) => updateAt(i, v[0], lat)}
          />
          <div style={{ display: "flex", gap: 4, alignItems: "flex-end" }}>
            <button type="button" onClick={() => move(i, -1)} disabled={i === 0}>
              ↑
            </button>
            <button type="button" onClick={() => move(i, 1)} disabled={i === vertices.length - 1}>
              ↓
            </button>
            <button type="button" onClick={() => removeAt(i)} disabled={vertices.length <= 3}>
              Remove
            </button>
          </div>
        </div>
      ))}
      <button type="button" onClick={addVertex} style={{ alignSelf: "flex-start" }}>
        + Point
      </button>
    </div>
  );
}
