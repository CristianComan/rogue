import type { Feature, FeatureCollection, Point } from "geojson";
import type { GeoJSONSource, Map as MapLibreMap } from "maplibre-gl";
import type { Receiver } from "../../../domain/types";

const SOURCE_ID = "receivers";
const LAYER_ID = "receivers-symbol";

const RECEIVER_COLORS: Record<Receiver["receiver_type"], string> = {
  monitor: "#2c7a63",
  tdoa: "#b85e17",
  aoa_doa: "#4c5c5e",
};

function toFeatureCollection(receivers: Receiver[]): FeatureCollection<Point> {
  return {
    type: "FeatureCollection",
    features: receivers.map((r): Feature<Point> => ({
      type: "Feature",
      id: r.id,
      geometry: { type: "Point", coordinates: r.position.coordinates as number[] },
      properties: {
        name: r.name,
        receiverType: r.receiver_type,
        color: RECEIVER_COLORS[r.receiver_type],
      },
    })),
  };
}

export function ensureReceiversLayer(map: MapLibreMap): void {
  if (map.getSource(SOURCE_ID)) return;

  map.addSource(SOURCE_ID, {
    type: "geojson",
    data: { type: "FeatureCollection", features: [] },
    promoteId: "id",
  });
  map.addLayer({
    id: LAYER_ID,
    type: "circle",
    source: SOURCE_ID,
    paint: {
      "circle-radius": 6,
      "circle-color": ["get", "color"],
      "circle-stroke-color": "#ffffff",
      "circle-stroke-width": 2,
    },
  });
}

export function syncReceiversLayer(map: MapLibreMap, receivers: Receiver[]): void {
  ensureReceiversLayer(map);
  const source = map.getSource(SOURCE_ID) as GeoJSONSource | undefined;
  source?.setData(toFeatureCollection(receivers));
}

export const RECEIVERS_INTERACTIVE_LAYER_IDS = [LAYER_ID];
