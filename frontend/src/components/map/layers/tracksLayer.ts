import type { Feature, FeatureCollection, LineString } from "geojson";
import type { GeoJSONSource, Map as MapLibreMap } from "maplibre-gl";
import { trajectoryPreviewGeoJSON } from "../../../domain/geojson";
import type { DroneMission } from "../../../domain/types";

const SOURCE_ID = "tracks";
const LAYER_ID = "tracks-line";

function toFeatureCollection(missions: DroneMission[]): FeatureCollection<LineString> {
  const features: Feature<LineString>[] = missions.map((mission) => ({
    type: "Feature",
    id: mission.id,
    geometry: trajectoryPreviewGeoJSON(mission.trajectory) as unknown as LineString,
    properties: { missionId: mission.id, name: mission.name },
  }));
  return { type: "FeatureCollection", features };
}

export function ensureTracksLayer(map: MapLibreMap): void {
  if (map.getSource(SOURCE_ID)) return;

  map.addSource(SOURCE_ID, { type: "geojson", data: { type: "FeatureCollection", features: [] } });
  map.addLayer({
    id: LAYER_ID,
    type: "line",
    source: SOURCE_ID,
    paint: { "line-color": "#b85e17", "line-width": 2, "line-dasharray": [2, 1.5] },
  });
}

export function syncTracksLayer(map: MapLibreMap, missions: DroneMission[]): void {
  ensureTracksLayer(map);
  const source = map.getSource(SOURCE_ID) as GeoJSONSource | undefined;
  source?.setData(toFeatureCollection(missions));
}
