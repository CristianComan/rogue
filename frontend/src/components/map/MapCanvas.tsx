import * as maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { useEffect, useRef, useState } from "react";
import type { DroneMission, Receiver, Zone } from "../../domain/types";
import type { Selection } from "../../state/selection";
import {
  DRONE_POSITIONS_INTERACTIVE_LAYER_IDS,
  syncDronePositionsLayer,
} from "./layers/dronePositionsLayer";
import { RECEIVERS_INTERACTIVE_LAYER_IDS, syncReceiversLayer } from "./layers/receiversLayer";
import { syncTracksLayer } from "./layers/tracksLayer";
import { WAYPOINTS_INTERACTIVE_LAYER_IDS, syncWaypointsLayer } from "./layers/waypointsLayer";
import { ZONES_INTERACTIVE_LAYER_IDS, syncZonesLayer } from "./layers/zonesLayer";

// Public vector basemap for dev — see the M3 design note in
// docs/architecture/implementation-plan.md on why this isn't self-hosted
// yet (useful geographic context for mission planning outweighs the lab-
// network-isolation concern here, which is about the SDR Agent network,
// not the operator's browser).
const BASE_STYLE_URL = "https://demotiles.maplibre.org/style.json";

export interface MapCanvasProps {
  zones: Zone[];
  missions: DroneMission[];
  receivers: Receiver[];
  scenarioTimeSeconds: number;
  selection?: Selection;
  onSelect?: (selection: Selection) => void;
}

function fitToContent(map: maplibregl.Map, zones: Zone[]): void {
  if (zones.length === 0) return;
  const bounds = new maplibregl.LngLatBounds();
  for (const zone of zones) {
    for (const ring of zone.polygon.coordinates) {
      for (const position of ring) {
        bounds.extend([position[0], position[1]]);
      }
    }
  }
  if (!bounds.isEmpty()) {
    map.fitBounds(bounds, { padding: 40, animate: false });
  }
}

export function MapCanvas({
  zones,
  missions,
  receivers,
  scenarioTimeSeconds,
  selection = null,
  onSelect,
}: MapCanvasProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const [ready, setReady] = useState(false);
  const hasFitBounds = useRef(false);

  useEffect(() => {
    if (!containerRef.current) return;

    const map = new maplibregl.Map({
      container: containerRef.current,
      style: BASE_STYLE_URL,
      center: [0, 0],
      zoom: 1,
    });
    mapRef.current = map;

    // "style.load" fires once the style spec is parsed and its own
    // sources/layers exist — the documented point at which custom layers
    // are safe to add. "load" instead waits for every basemap tile in the
    // initial viewport to finish downloading, which ties our own scenario
    // layers to basemap tile availability for no reason (and can hang
    // indefinitely if the tile CDN is unreachable, independent of whether
    // the style document itself loaded).
    map.on("style.load", () => setReady(true));

    return () => {
      map.remove();
      mapRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- map is created once
  }, []);

  // Click-to-select, wired once the map is ready.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready || !onSelect) return;

    const handlers: Array<[string, (e: maplibregl.MapLayerMouseEvent) => void]> = [
      ...ZONES_INTERACTIVE_LAYER_IDS.map(
        (id): [string, (e: maplibregl.MapLayerMouseEvent) => void] => [
          id,
          (e) => {
            const zoneId = e.features?.[0]?.id;
            if (zoneId !== undefined) onSelect({ kind: "zone", id: String(zoneId) });
          },
        ],
      ),
      ...RECEIVERS_INTERACTIVE_LAYER_IDS.map(
        (id): [string, (e: maplibregl.MapLayerMouseEvent) => void] => [
          id,
          (e) => {
            const receiverId = e.features?.[0]?.id;
            if (receiverId !== undefined) onSelect({ kind: "receiver", id: String(receiverId) });
          },
        ],
      ),
      ...WAYPOINTS_INTERACTIVE_LAYER_IDS.map(
        (id): [string, (e: maplibregl.MapLayerMouseEvent) => void] => [
          id,
          (e) => {
            const props = e.features?.[0]?.properties;
            if (props) {
              onSelect({
                kind: "waypoint",
                missionId: props.missionId as string,
                sequenceIndex: props.sequenceIndex as number,
              });
            }
          },
        ],
      ),
      ...DRONE_POSITIONS_INTERACTIVE_LAYER_IDS.map(
        (id): [string, (e: maplibregl.MapLayerMouseEvent) => void] => [
          id,
          (e) => {
            const missionId = e.features?.[0]?.properties?.missionId;
            if (missionId) onSelect({ kind: "mission", id: String(missionId) });
          },
        ],
      ),
    ];

    for (const [layerId, handler] of handlers) {
      map.on("click", layerId, handler);
    }
    return () => {
      for (const [layerId, handler] of handlers) {
        map.off("click", layerId, handler);
      }
    };
  }, [ready, onSelect]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    syncZonesLayer(map, zones);
    if (!hasFitBounds.current && zones.length > 0) {
      fitToContent(map, zones);
      hasFitBounds.current = true;
    }
  }, [ready, zones]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    syncTracksLayer(map, missions);
    const isSelected = (missionId: string, sequenceIndex: number) =>
      selection?.kind === "waypoint" &&
      selection.missionId === missionId &&
      selection.sequenceIndex === sequenceIndex;
    syncWaypointsLayer(map, missions, isSelected);
  }, [ready, missions, selection]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    syncReceiversLayer(map, receivers);
  }, [ready, receivers]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    syncDronePositionsLayer(map, missions, scenarioTimeSeconds);
  }, [ready, missions, scenarioTimeSeconds]);

  return (
    <div ref={containerRef} style={{ width: "100%", height: "100%" }} data-testid="map-canvas" />
  );
}
