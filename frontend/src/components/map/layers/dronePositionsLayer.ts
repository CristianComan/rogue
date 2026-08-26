import type { Feature, Point } from "geojson";
import type { GeoJSONSource, Map as MapLibreMap } from "maplibre-gl";
import { evaluateScenarioState } from "../../../domain/missionEvaluator";
import type { DroneMission } from "../../../domain/types";

const SOURCE_ID = "drone-positions";
const LAYER_ID = "drone-positions-symbol";

export function ensureDronePositionsLayer(map: MapLibreMap): void {
  if (map.getSource(SOURCE_ID)) return;

  map.addSource(SOURCE_ID, { type: "geojson", data: { type: "FeatureCollection", features: [] } });
  map.addLayer({
    id: LAYER_ID,
    type: "circle",
    source: SOURCE_ID,
    paint: {
      "circle-radius": 7,
      "circle-color": [
        "match",
        ["get", "phase"],
        "before_start",
        "#8fa3a1",
        "completed",
        "#4c5c5e",
        "#b85e17",
      ],
      "circle-stroke-color": "#ffffff",
      "circle-stroke-width": 2,
    },
  });
}

/** The layer that delivers the M3 exit criterion: multi-drone visual playback. */
export function syncDronePositionsLayer(
  map: MapLibreMap,
  missions: DroneMission[],
  scenarioTimeSeconds: number,
): void {
  ensureDronePositionsLayer(map);
  const source = map.getSource(SOURCE_ID) as GeoJSONSource | undefined;
  if (!source) return;

  const states = evaluateScenarioState(missions, scenarioTimeSeconds);
  const features: Feature<Point>[] = missions.map((mission) => {
    const state = states.get(mission.id);
    return {
      type: "Feature",
      id: mission.id,
      geometry: { type: "Point", coordinates: state ? state.positionLonLat : [0, 0] },
      properties: {
        missionId: mission.id,
        name: mission.name,
        phase: state?.phase ?? "before_start",
        headingDeg: state?.headingDeg ?? 0,
        speedMps: state?.speedMps ?? 0,
      },
    };
  });

  source.setData({ type: "FeatureCollection", features });
}

export const DRONE_POSITIONS_INTERACTIVE_LAYER_IDS = [LAYER_ID];
