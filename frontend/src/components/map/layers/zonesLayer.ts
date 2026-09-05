import type { FeatureCollection, Polygon } from "geojson";
import type { GeoJSONSource, Map as MapLibreMap } from "maplibre-gl";
import type { Zone } from "../../../domain/types";

const SOURCE_ID = "zones";
const FILL_LAYER_ID = "zones-fill";
const OUTLINE_LAYER_ID = "zones-outline";

const ZONE_COLORS: Record<Zone["zone_type"], string> = {
  operational_area: "#2c7a63",
  no_transmit: "#a3311f",
  no_fly: "#a3311f",
  restricted: "#a34b1f",
  custom: "#4c5c5e",
};

function toFeatureCollection(zones: Zone[]): FeatureCollection<Polygon> {
  return {
    type: "FeatureCollection",
    features: zones.map((zone) => ({
      type: "Feature",
      id: zone.id,
      geometry: zone.polygon as unknown as Polygon,
      properties: {
        zoneType: zone.zone_type,
        label: zone.label ?? "",
        color: ZONE_COLORS[zone.zone_type],
      },
    })),
  };
}

export function ensureZonesLayer(map: MapLibreMap): void {
  if (map.getSource(SOURCE_ID)) return;

  map.addSource(SOURCE_ID, {
    type: "geojson",
    data: { type: "FeatureCollection", features: [] },
    promoteId: "id",
  });
  map.addLayer({
    id: FILL_LAYER_ID,
    type: "fill",
    source: SOURCE_ID,
    paint: {
      "fill-color": ["get", "color"],
      "fill-opacity": ["case", ["boolean", ["feature-state", "selected"], false], 0.35, 0.15],
    },
  });
  map.addLayer({
    id: OUTLINE_LAYER_ID,
    type: "line",
    source: SOURCE_ID,
    paint: {
      "line-color": ["get", "color"],
      "line-width": ["case", ["boolean", ["feature-state", "selected"], false], 3, 1.5],
    },
  });
}

export function syncZonesLayer(map: MapLibreMap, zones: Zone[]): void {
  ensureZonesLayer(map);
  const source = map.getSource(SOURCE_ID) as GeoJSONSource | undefined;
  source?.setData(toFeatureCollection(zones));
}

export const ZONES_INTERACTIVE_LAYER_IDS = [FILL_LAYER_ID];
export { SOURCE_ID as ZONES_SOURCE_ID };
