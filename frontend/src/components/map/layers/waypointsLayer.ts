import type { Feature, FeatureCollection, Point } from "geojson";
import type { GeoJSONSource, Map as MapLibreMap } from "maplibre-gl";
import type { DroneMission } from "../../../domain/types";

const SOURCE_ID = "waypoints";
const LAYER_ID = "waypoints-circle";

interface WaypointProps {
  missionId: string;
  sequenceIndex: number;
  selected: boolean;
}

function toFeatureCollection(
  missions: DroneMission[],
  isSelected: (missionId: string, sequenceIndex: number) => boolean,
): FeatureCollection<Point, WaypointProps> {
  const features: Feature<Point, WaypointProps>[] = [];
  for (const mission of missions) {
    for (const wp of mission.trajectory.waypoints) {
      features.push({
        type: "Feature",
        geometry: { type: "Point", coordinates: wp.position.coordinates as number[] },
        properties: {
          missionId: mission.id,
          sequenceIndex: wp.sequence_index,
          selected: isSelected(mission.id, wp.sequence_index),
        },
      });
    }
  }
  return { type: "FeatureCollection", features };
}

export function ensureWaypointsLayer(map: MapLibreMap): void {
  if (map.getSource(SOURCE_ID)) return;

  map.addSource(SOURCE_ID, { type: "geojson", data: { type: "FeatureCollection", features: [] } });
  map.addLayer({
    id: LAYER_ID,
    type: "circle",
    source: SOURCE_ID,
    paint: {
      "circle-radius": ["case", ["get", "selected"], 7, 5],
      "circle-color": "#ffffff",
      "circle-stroke-color": "#b85e17",
      "circle-stroke-width": ["case", ["get", "selected"], 3, 2],
    },
  });
}

export function syncWaypointsLayer(
  map: MapLibreMap,
  missions: DroneMission[],
  isSelected: (missionId: string, sequenceIndex: number) => boolean = () => false,
): void {
  ensureWaypointsLayer(map);
  const source = map.getSource(SOURCE_ID) as GeoJSONSource | undefined;
  source?.setData(toFeatureCollection(missions, isSelected));
}

export const WAYPOINTS_INTERACTIVE_LAYER_IDS = [LAYER_ID];
