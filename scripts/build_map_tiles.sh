#!/usr/bin/env bash
# Builds a self-hosted vector-tile basemap (roads/streets, no imagery) for
# the docker-compose `tiles` service (see docs/testing/manual-verification-guide.md).
#
# The public demotiles.maplibre.org CDN that frontend/src/components/map/MapCanvas.tsx
# used by default isn't reachable from every operator's browser (confirmed:
# not a general network-isolation issue, just that one CDN) — rather than
# depend on a third-party service's reachability, this builds real
# OpenStreetMap-derived map data locally, the same way ROGUE already runs
# its own Postgres/MinIO/NATS instead of depending on external ones.
#
# Scoped to the Berlin area the example/test scenarios already use
# (examples/scenarios/single-drone-orbit.yaml and the manual-verification
# scenarios: roughly 13.0-13.6 deg E, 52.0-52.6 deg N), padded a bit for
# pan/zoom room. Not a general-purpose basemap builder — re-run with
# different SOURCE_PBF_URL/BOUNDS values (see below) to cover another area.
#
# Output (map-tiles/, gitignored — generated data, never committed, same
# treatment as recordings/):
#   map-tiles/sources/berlin-latest.osm.pbf  (downloaded once, cached)
#   map-tiles/berlin.mbtiles                 (built by planetiler)
#
# Usage:
#   scripts/build_map_tiles.sh
#   docker-compose up -d tiles   # serves map-tiles/berlin.mbtiles

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MAP_TILES_DIR="$REPO_ROOT/map-tiles"
SOURCES_DIR="$MAP_TILES_DIR/sources"
SOURCE_PBF_URL="https://download.geofabrik.de/europe/germany/berlin-latest.osm.pbf"
SOURCE_PBF="$SOURCES_DIR/berlin-latest.osm.pbf"
OUTPUT_MBTILES="berlin.mbtiles"
# min_lon,min_lat,max_lon,max_lat — the example/test scenarios' area
# (13.0,52.0)-(13.6,52.6), padded by ~0.2 deg on each side.
BOUNDS="12.8,51.8,13.8,52.8"

mkdir -p "$SOURCES_DIR"

if [ -f "$SOURCE_PBF" ]; then
  echo "using cached $SOURCE_PBF"
else
  # Geofabrik's "-latest" URL 302-redirects to a dated filename; following
  # the redirect as part of a single GET has been observed to intermittently
  # 502 on their end for a large file, while resolving it first and GETting
  # the dated URL directly does not. Resolve explicitly rather than relying
  # on curl -L for the whole transfer.
  RESOLVED_URL=$(curl -fsI "$SOURCE_PBF_URL" | grep -i '^location:' | tr -d '\r' | awk '{print $2}')
  RESOLVED_URL="${RESOLVED_URL:-$SOURCE_PBF_URL}"
  echo "downloading $RESOLVED_URL..."
  curl -fL --retry 3 --retry-delay 2 -o "$SOURCE_PBF.tmp" "$RESOLVED_URL"
  mv "$SOURCE_PBF.tmp" "$SOURCE_PBF"
fi

echo "building $MAP_TILES_DIR/$OUTPUT_MBTILES (bounds=$BOUNDS)..."
docker run --rm -v "$MAP_TILES_DIR:/data" ghcr.io/onthegomap/planetiler:latest \
  --osm_path="/data/sources/$(basename "$SOURCE_PBF")" \
  --output="/data/$OUTPUT_MBTILES" \
  --bounds="$BOUNDS" \
  --download \
  --force

echo "done: $MAP_TILES_DIR/$OUTPUT_MBTILES"
echo "next: docker-compose up -d tiles"
