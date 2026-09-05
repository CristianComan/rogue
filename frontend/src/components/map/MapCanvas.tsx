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

// Two selectable basemap sources — see the in-editor selector below.
// "offline": self-hosted vector tiles (roads/streets, OpenStreetMap-derived,
// built by scripts/build_map_tiles.sh, served by docker-compose's `tiles`
// service), full OpenMapTiles-schema detail (roads, buildings, water,
// admin, place labels), but only within the built area — see
// scripts/build_map_tiles.sh's BOUNDS. "online": OpenFreeMap's "liberty"
// style (https://openfreemap.org) — free, unlimited, no API key, real
// global OSM-derived detail comparable to the offline source. Previously
// pointed at demotiles.maplibre.org, MapLibre's own bare library demo
// tileset (country borders only, by design — it was never going to show
// streets, regardless of any rendering fix, on any browser).
type MapSource = "offline" | "online";

const ONLINE_STYLE_URL = "https://tiles.openfreemap.org/styles/liberty";
const OFFLINE_STYLE_URL = import.meta.env.VITE_MAP_STYLE_URL || null;

// Default camera when there's no zone/mission/receiver content to fit to
// (see fitToContent below) — centered on Berlin, where both the example
// scenarios and the offline tileset's coverage area already are, so an
// empty scenario opens over real, detailed map content instead of a [0, 0]
// world view where even a fully-detailed basemap only has continent-scale
// borders to show.
const DEFAULT_CENTER: [number, number] = [13.4, 52.5];
const DEFAULT_ZOOM = 10;

function styleUrlFor(source: MapSource): string {
  if (source === "offline" && OFFLINE_STYLE_URL) return OFFLINE_STYLE_URL;
  return ONLINE_STYLE_URL;
}

// Falls back to this if neither selectable source (online or offline) can
// be reached at all — no external requests, so it always loads. The
// scenario's own layers (zones/tracks/waypoints/receivers/drone positions,
// all local GeoJSON — components/map/layers/*.ts) don't depend on the
// basemap and render fine on top of it; without this fallback "style.load"
// never fires and the map stays permanently blank.
//
// Deliberately a data: URL (string), not a plain style object: MapLibre's
// setStyle() routes a *string* through Style.loadURL() (a plain fetch, no
// extra gating), but routes an *object* through Style.loadJSON(), which
// internally awaits one requestAnimationFrame tick
// (browser.frameAsync -> requestAnimationFrame, see
// node_modules/maplibre-gl/dist/maplibre-gl-dev.mjs's Style class) before it
// even starts loading. rAF is paused/throttled for backgrounded or
// not-currently-composited tabs, so a plain-object fallback can silently
// never apply — confirmed directly: constructing a Map with the same style
// as an object never fired "style.load", but constructing it with this
// data: URL fired it immediately. A data: URL has no network cost and no
// CORS/origin restriction, so this is free precision, not a tradeoff.
const OFFLINE_FALLBACK_STYLE_URL =
  "data:application/json," +
  encodeURIComponent(
    JSON.stringify({
      version: 8,
      sources: {},
      layers: [{ id: "background", type: "background", paint: { "background-color": "#dde5e3" } }],
    }),
  );

// Loads `url` on `map`, falling back once to the flat-color style if it
// fails, and calling `onLoaded` when *something* finishes loading (real
// style or fallback) — shared by the initial mount and the online/offline
// selector switching sources later, so both go through the exact same
// { diff: false } + fallback logic (see OFFLINE_FALLBACK_STYLE_URL's
// comment for why diff:false matters).
function applyStyle(map: maplibregl.Map, url: string, onLoaded: () => void): void {
  let settled = false;
  const onStyleLoad = () => {
    if (settled) return;
    settled = true;
    map.off("error", onError);
    onLoaded();
  };
  const onError = () => {
    if (settled) return;
    settled = true;
    map.off("style.load", onStyleLoad);
    map.once("style.load", onLoaded);
    map.setStyle(OFFLINE_FALLBACK_STYLE_URL, { diff: false });
  };
  map.once("style.load", onStyleLoad);
  map.once("error", onError);
  map.setStyle(url, { diff: false });
}

export interface MapCanvasProps {
  zones: Zone[];
  missions: DroneMission[];
  receivers: Receiver[];
  scenarioTimeSeconds: number;
  selection?: Selection;
  onSelect?: (selection: Selection) => void;
}

// Zones, mission waypoints and receivers are all fair game for the initial
// camera fit — a scenario with missions/receivers but no zones (a very
// normal starting point; zones are optional) previously left the map at its
// hardcoded [0, 0]/zoom 1 default forever, where real-world content is far
// too small to see. Bounds-fitting from *any* of the three is the fix.
function fitToContent(
  map: maplibregl.Map,
  zones: Zone[],
  missions: DroneMission[],
  receivers: Receiver[],
): void {
  const bounds = new maplibregl.LngLatBounds();
  for (const zone of zones) {
    for (const ring of zone.polygon.coordinates) {
      for (const position of ring) {
        bounds.extend([position[0], position[1]]);
      }
    }
  }
  for (const mission of missions) {
    for (const waypoint of mission.trajectory.waypoints) {
      bounds.extend([waypoint.position.coordinates[0], waypoint.position.coordinates[1]]);
    }
  }
  for (const receiver of receivers) {
    bounds.extend([receiver.position.coordinates[0], receiver.position.coordinates[1]]);
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
  // "online" (OpenFreeMap) is the default: full global coverage, whereas
  // "offline" only has detail within scripts/build_map_tiles.sh's built
  // area (Berlin) — offline is still there as a fallback/no-internet option
  // via the selector, just not the first thing shown.
  const [mapSource, setMapSource] = useState<MapSource>("online");
  const mountedSource = useRef(mapSource);

  useEffect(() => {
    if (!containerRef.current) return;

    // No `style` option here — applyStyle() sets it right after construction
    // (see its own comment), the same path used when the selector below
    // switches sources later, rather than duplicating the load/fallback
    // logic once for the constructor and again for switches.
    const map = new maplibregl.Map({
      container: containerRef.current,
      center: DEFAULT_CENTER,
      zoom: DEFAULT_ZOOM,
      // Compact (icon-only, collapsed) is already MapLibre's default, but
      // its *default* attribution control also always adds its own
      // "MapLibre" self-promo link alongside whatever the loaded style
      // itself requires — dropping customAttribution here keeps only the
      // real, required credit (e.g. OpenFreeMap/OpenStreetMap/OpenMapTiles,
      // whichever style is active), not MapLibre's own. The control itself
      // can't be removed outright: both basemap sources' data is
      // OSM-derived and their terms require visible attribution.
      attributionControl: { compact: true },
    });
    mapRef.current = map;
    applyStyle(map, styleUrlFor(mountedSource.current), () => setReady(true));

    return () => {
      map.remove();
      mapRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- map is created once; mountedSource is only read on this first run
  }, []);

  // The online/offline selector below switching sources after the initial
  // mount. `ready` resets around the switch so every layer-sync effect below
  // re-adds its source/layer onto the new Style object (setStyle() discards
  // the previous one's custom sources/layers entirely).
  useEffect(() => {
    const map = mapRef.current;
    if (!map || mapSource === mountedSource.current) return;
    mountedSource.current = mapSource;
    setReady(false);
    applyStyle(map, styleUrlFor(mapSource), () => setReady(true));
  }, [mapSource]);

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
  }, [ready, zones]);

  // Fits the camera once, the first time any zone/mission/receiver content
  // appears — not repeated afterward, so it never fights a user's own pan/zoom.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready || hasFitBounds.current) return;
    if (zones.length === 0 && missions.length === 0 && receivers.length === 0) return;
    fitToContent(map, zones, missions, receivers);
    hasFitBounds.current = true;
  }, [ready, zones, missions, receivers]);

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
    <div style={{ position: "relative", width: "100%", height: "100%" }}>
      <div ref={containerRef} style={{ width: "100%", height: "100%" }} data-testid="map-canvas" />
      <select
        aria-label="Basemap source"
        data-testid="map-source-select"
        value={mapSource}
        onChange={(e) => setMapSource(e.target.value as MapSource)}
        style={{
          position: "absolute",
          top: 8,
          right: 8,
          zIndex: 1,
          font: "12px/1.4 system-ui, sans-serif",
          padding: "2px 4px",
        }}
      >
        <option value="offline" disabled={!OFFLINE_STYLE_URL}>
          Offline (self-hosted)
        </option>
        <option value="online">Online (public)</option>
      </select>
    </div>
  );
}
