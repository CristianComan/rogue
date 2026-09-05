# Checking ROGUE yourself — manual verification guide (M0–M7)

A hands-on walkthrough for verifying what's been built so far, milestone by
milestone, without having to read the code. Everything is copy/paste — run
each block in a terminal from the repo root
(`/home/cristian/Programming/python/26.IC/rogue`).

| Milestone | What it is | Verify by |
|---|---|---|
| M0 | Repo/CI shell, health endpoint | `curl` + a test |
| M1 | Scenario domain model (typed schema, no server) | a Python script |
| M2 | Scenario persistence/API | `curl` against a running server |
| M3 | Map + trajectory editor | clicking around a browser UI |
| M4 | SigMF recording catalogue | `curl` against a running server |
| M5 | RF spectrum planner | `curl` against a running server |
| — | Recording schedule + spectrum waterfall (supplemental) | `curl` + a browser UI |
| M6 | Replay Plan compiler | `curl` against a running server |
| M7 | Simulated SDR execution | `curl` against a running server |
| — | Real drone RF corpus loader (`scripts/ingest_drone_corpus.py`) | run the script, then `curl`/`psql` |

Each section is independent — jump to whichever milestone you want to check.
Section 0 is shared setup everything else depends on.

## 0. One-time setup

```bash
cd /home/cristian/Programming/python/26.IC/rogue
source .venv/bin/activate
```

M2/M3/M4/M5/M6 need Postgres and MinIO (S3-compatible storage) running locally.
M0/M1 don't need anything beyond the venv.

### Starting the docker containers

`docker-compose.yml` defines the whole stack:

| Service | What it's for | Needed for this guide? |
|---|---|---|
| `postgres` | PostgreSQL/PostGIS — every persisted scenario/draft/version/recording/replay plan | Yes (M2+) |
| `minio` | S3-compatible object storage — SigMF recording bytes | Yes (M4+) |
| `minio-init` | One-shot job that creates the `rogue` bucket in MinIO, then exits | Yes (M4+, runs once) |
| `nats` | JetStream message broker — SDR Agent command/telemetry protocol | Not yet — no section below talks to it |
| `api` | The FastAPI backend, containerized | No — this guide runs it directly with `uvicorn --reload` instead for a faster edit/reload loop; use this if you'd rather not set up a local Python env |
| `ui` | The Vite frontend, containerized | No — this guide runs `frontend/dev.sh` directly instead, same reason |
| `tiles` | Self-hosted MapLibre basemap tiles | Optional, M3 only — see that section |
| `simulated-agent` | Placeholder simulated SDR Agent | Not yet exercised by any section below |

For everything in this guide you only need `postgres`, `minio` and
`minio-init` running. Check whether they already are:

```bash
docker ps --filter "name=rogue-postgres" --filter "name=rogue-minio"
```

If that prints nothing, start them:

```bash
docker compose up -d postgres minio minio-init
```

(If `docker compose up` errors with `KeyError: 'ContainerConfig'`, the
containers exist but are stale — find them with `docker ps -a --filter
name=rogue` and start them by container ID instead, e.g. `docker start
<postgres_id> <minio_id>`.)

Confirm they're actually healthy, not just started:

```bash
docker compose ps
```

`postgres` and `minio` should show `Up`/`healthy`. `minio-init` should show
`Exited (0)` — it's a one-shot job, not a long-running service, so "exited
successfully" is what a healthy run looks like for it, not a failure.

Two things you won't need for anything in this guide, but worth knowing
about: bringing up the *entire* stack, including the containerized API/UI
(e.g. to test the `docker compose build` path itself, not just local dev
servers):

```bash
docker compose up -d
```

and tearing everything down:

```bash
docker compose down
```

Add `-v` to that last one only if you want a clean slate — it also deletes
the Postgres/MinIO/NATS data volumes, i.e. every scenario/recording/replay
plan you've registered.

### Full containerized stack: two things that will trip you up

**Running local `uvicorn`/`frontend/dev.sh` *and* the full stack at the same
time.** `api` and `ui` bind the same host ports (`8000`/`5173`) their local
dev-server equivalents use. If you `docker compose up -d` (the full stack)
and then also try `uvicorn rogue.main:app --reload --app-dir backend`,
you'll get `ERROR: [Errno 98] Address already in use` — that's the `api`
container already holding port 8000, not a bug. Pick one:

```bash
docker compose stop api  # frees 8000 for local uvicorn; postgres/minio/etc. keep running
```
```bash
docker compose up -d api  # or the reverse: give the port back to the container
```

**A stale local image after a Node or settings change.** The `ui` image is
pinned to `frontend/Dockerfile`'s `FROM node:24-slim` — a maplibre-gl
tooling dependency (`@mapbox/jsonlint-lines-primitives`) requires Node >=22,
and `.npmrc`'s `engine-strict=true` makes `npm ci` hard-fail rather than
warn on a mismatch, so if you ever see `EBADENGINE`/`Not compatible with
your version of node` while building `ui`, that image predates the Node 24
bump — `docker compose build ui` picks up the current Dockerfile. Similarly,
if `api` crashes on startup with `pydantic_settings.exceptions.SettingsError`
mentioning `cors_allowed_origins`, that image predates
`backend/rogue/settings.py`'s `NoDecode` fix for comma-separated
`ROGUE_CORS_ALLOWED_ORIGINS` values — `docker compose build api` picks up
the fix. Check what actually crashed with:

```bash
docker compose logs api --tail 40
```

Then make sure the database schema is current:

```bash
alembic upgrade head
```

## Automated checks (covers all milestones)

These are the same commands CI/review runs — one shot at everything:

```bash
ruff check backend tests
```
Expect: `All checks passed!`

```bash
cd backend && mypy rogue && cd ..
```
Expect: `Success: no issues found in 57 source files`

```bash
pytest tests/unit -q
```
Expect: `254 passed`. (If Postgres isn't running, the persistence/API tests
will error out with a connection-refused message — that's the DB, not a
code problem; go back to section 0.)

To scope the test run to one milestone:

```bash
pytest tests/unit/test_health.py -v                                  # M0
pytest tests/unit/domain -v                                          # M1
pytest tests/unit/persistence/test_repository.py tests/unit/api/test_scenarios.py -v   # M2
pytest tests/unit/catalogue tests/unit/persistence/test_catalogue.py tests/unit/api/test_recordings.py -v   # M4 + recording schedule/waterfall
pytest tests/unit/spectrum tests/unit/persistence/test_spectrum.py tests/unit/api/test_spectrum_planner.py -v   # M5
pytest tests/unit/domain/test_rf.py tests/unit/domain/test_recording.py tests/unit/domain/test_validation.py -v   # recording schedule/waterfall domain
pytest tests/unit/compiler tests/unit/persistence/test_replay.py tests/unit/api/test_replay_compiler.py -v   # M6
pytest tests/unit/domain/test_run.py tests/unit/execution tests/unit/persistence/test_run_execution.py tests/unit/api/test_runs.py -v   # M7
```
(M3 is a frontend feature — its checks are `npm run typecheck`, `npm test`
and `npm run e2e` from `frontend/`, see the M3 section below.)

The rest of this guide is about *seeing it work*, not just tests passing.

## M0 — repository shell & health check

Start the server:

```bash
uvicorn rogue.main:app --reload --app-dir backend
```

In another terminal:

```bash
curl -s http://localhost:8000/health -w "\nHTTP %{http_code}\n"
```

Expect `{"status":"ok","service":"rogue-api"}` and `HTTP 200`. That's the
whole of M0's scope — a running process with a health check CI/Compose can
poll. Leave the server running; every other section uses it.

## M1 — scenario domain model

M1 has no HTTP surface — it's the typed Pydantic schema everything else is
built on (`backend/rogue/domain/`), proven by round-tripping the example
scenario at `examples/scenarios/single-drone-orbit.yaml`. Run this with the
venv active:

```bash
PYTHONPATH=backend python3 - <<'EOF'
from rogue.domain.scenario import ScenarioVersion
from rogue.domain.serialization import from_yaml, to_yaml, to_json
from rogue.domain.validation import validate_scenario_version

text = open("examples/scenarios/single-drone-orbit.yaml").read()
version = from_yaml(ScenarioVersion, text)
print("parsed:", version.scenario_id, "version", version.version_number)
print("missions:", [m.name for m in version.missions])

findings = validate_scenario_version(version)
print("validation findings:", findings)

restored = from_yaml(ScenarioVersion, to_yaml(version))
print("round-trip equal:", restored == version)
EOF
```

Expect: it parses, prints one mission (`recon-1`), an empty findings list
(the fixture is valid), and `round-trip equal: True`. If you break the
fixture on purpose (e.g. delete the `missions:` block) and rerun, you should
see a `pydantic.ValidationError` instead — that's the schema doing its job.

## M2 — scenario persistence & API

With the server from M0 still running:

```bash
SCENARIO=$(curl -s -X POST http://localhost:8000/scenarios \
  -H "Content-Type: application/json" \
  -d '{
    "name": "manual-check scenario",
    "owner": "manual-check",
    "area_of_operation": {"type":"Polygon","coordinates":[[[13.0,52.0],[13.6,52.0],[13.6,52.6],[13.0,52.6],[13.0,52.0]]]}
  }')
echo "$SCENARIO" | python3 -m json.tool
SCENARIO_ID=$(echo "$SCENARIO" | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])")
```

Create a draft on it, validate it, and publish:

```bash
DRAFT=$(curl -s -X POST http://localhost:8000/scenarios/$SCENARIO_ID/drafts \
  -H "Content-Type: application/json" -d '{"author":"manual-check"}')
echo "$DRAFT" | python3 -m json.tool
DRAFT_ID=$(echo "$DRAFT" | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])")

curl -s -X POST http://localhost:8000/scenarios/$SCENARIO_ID/drafts/$DRAFT_ID/validate | python3 -m json.tool

curl -s -X POST http://localhost:8000/scenarios/$SCENARIO_ID/drafts/$DRAFT_ID/publish | python3 -m json.tool

curl -s http://localhost:8000/scenarios/$SCENARIO_ID/versions/1 | python3 -m json.tool
```

Expect: the draft comes back with `"revision": 0` and empty
missions/zones/receivers; `validate` returns one `"warning"`-severity
`empty_scenario` finding (not blocking — an empty scenario is legal, just
noteworthy); `publish` returns `version_number: 1` carrying that same
finding; and `GET .../versions/1` returns the identical, now-immutable
version. This is the same scenario the M3 section below opens in the UI.

## M3 — map + trajectory editor

This is a frontend feature — you click through a browser instead of curling.

### Basemap: self-hosted map tiles (one-time, optional but recommended)

The map needs a basemap style to show roads/streets under the scenario's own
zones/tracks/waypoints/receivers. `MapCanvas.tsx` tries three things in
order: (1) `VITE_MAP_STYLE_URL` if set — a self-hosted tile service, see
below; (2) the public `demotiles.maplibre.org` CDN, which isn't reachable
from every network; (3) a flat offline-color fallback with no basemap detail
at all, just so the scenario's own layers still render on *something*. For
real streets, build the self-hosted tiles once:

```bash
scripts/build_map_tiles.sh
```

This downloads a Berlin OSM extract (~100MB, cached after the first run)
plus some shared low-zoom water/coastline datasets planetiler needs
regardless of area (~1.3GB combined, also cached — this is the slow part,
only happens once) and builds `map-tiles/berlin.mbtiles`, scoped to the area
the example/test scenarios already use. Then:

```bash
docker compose up -d tiles
```

`frontend/.env.development` already points a plain `npm run dev` at
`http://localhost:8081/styles/basic-preview/style.json` (tileserver-gl's
auto-generated style name for an mbtiles it's given with no config.json —
confirm at `http://localhost:8081/styles.json` if you rebuild with a
differently-named file); the `ui` compose service gets the same URL via
`VITE_MAP_STYLE_URL`. Confirm it's serving real data:

```bash
curl -s http://localhost:8081/styles/basic-preview/style.json | python3 -m json.tool | head -20
```

Expect a real MapLibre style document with vector `sources` referencing
`berlin.mbtiles` (not the flat single-layer fallback). Skip this whole
section if you don't need to see real map detail — the flat-color fallback
still lets you verify every other M3 behavior below.

Start the dev server. The machine's Node is now consolidated to a single
nvm-managed v24 LTS (see `frontend/.nvmrc`), so a plain `npm run dev` from
`frontend/` works fine in a normal interactive terminal — but
`frontend/dev.sh` is still the more robust choice since it explicitly
resolves `nvm use default` itself rather than relying on your shell already
having done so (matters for non-interactive launchers, or if some other
project's `nvm use` is still active in that terminal):

```bash
frontend/dev.sh
```

Open **http://localhost:5173** in a browser. You should land on the
scenario library page, listing scenarios from the M2 database — including
`manual-check scenario` if you ran the M2 section above.

1. Click **Edit** on a scenario to open the editor. You should see a
   MapLibre map, a timeline scrubber at the bottom (`t = 0.0s / ...`), and
   `+ Zone` / `+ Mission` / `+ Receiver` / `+ Timeline event` buttons.
2. Click **+ Mission**. A drone mission with a default 2-waypoint trajectory
   appears; the header changes to `revision 0 · unsaved changes` and the
   timeline extends to cover the new mission's duration.
3. Click **Save**. The header should change to `revision 1 · saved` — this
   is a real `PUT` to the M2 draft-update endpoint with optimistic
   concurrency (the `revision` number), not local-only UI state.
4. Click **Validate**, then **Publish**, then use **← Library** to go back
   — the scenario's "Current version" column should now say `published`.
5. Click **Play** on the timeline to scrub through the mission and confirm
   the drone position on the map advances with it.

If you want proof this isn't just visual: refresh the page after step 3.
The mission you added should still be there — it came back from Postgres
through the M2 API, not from browser state.

Automated checks for this milestone, from `frontend/`:

```bash
npm run typecheck
npm test
npm run e2e   # needs the backend + frontend dev servers running
```

## M4 — SigMF recording catalogue

You'll do three kinds of checks here:

1. **API check via the browser** — click through the interactive docs, no code.
2. **End-to-end check via curl** — actually register a fake recording and see
   it come back out of the catalogue.

(Automated lint/type/test checks for M4 are already covered above.)

### Look at the API in your browser

With the server from M0 still running, open **http://localhost:8000/docs**.
You'll see a `recordings` section:

- `POST /recordings` — register a SigMF asset pair
- `GET /recordings` — list the catalogue
- `GET /recordings/{recording_id}` — fetch one
- `GET /recordings/{recording_id}/versions` — version history

Expand any of them and click "Try it out" to fire a real request against
your local server. `GET /recordings` should return `200` with a JSON array
— that alone confirms the route, DB connection and response schema all
work.

To register something real through this UI, you need object keys that
actually exist in MinIO — that's what the next part sets up.

### End-to-end: register a real recording

**1. Upload a tiny synthetic SigMF pair to MinIO.** SigMF recordings
normally come from real captures, but the catalogue only cares that the two
objects exist and are internally consistent, so a synthetic one is enough
to exercise the whole path. Save this as `/tmp/upload_test_sigmf.py` and run
it (with the venv still active):

```python
import hashlib, json, struct
import boto3

# 100 fake complex float32 (cf32_le) samples — 8 bytes each.
samples = b"".join(struct.pack("<ff", 0.001 * i, -0.001 * i) for i in range(100))
sha512 = hashlib.sha512(samples).hexdigest()

meta = {
    "global": {
        "core:datatype": "cf32_le",
        "core:sample_rate": 1_000_000,
        "core:sha512": sha512,
    },
    "captures": [{"core:sample_start": 0, "core:frequency": 2_400_000_000}],
    "annotations": [],
}

s3 = boto3.client(
    "s3",
    endpoint_url="http://localhost:9000",
    aws_access_key_id="rogue",
    aws_secret_access_key="rogue_dev_password",
)
s3.put_object(Bucket="rogue", Key="manual-check/test.sigmf-meta", Body=json.dumps(meta).encode())
s3.put_object(Bucket="rogue", Key="manual-check/test.sigmf-data", Body=samples)
print("uploaded manual-check/test.sigmf-meta and manual-check/test.sigmf-data")
```

```bash
python /tmp/upload_test_sigmf.py
```

**2. Register it through the API.**

```bash
curl -s -X POST http://localhost:8000/recordings \
  -H "Content-Type: application/json" \
  -d '{
    "metadata_object_key": "manual-check/test.sigmf-meta",
    "data_object_key": "manual-check/test.sigmf-data",
    "provenance": "manual check"
  }' | python3 -m json.tool
```

Expect a `201`-shaped body: a `"recording"` object with a generated `id`,
`version: 1`, the computed `sample_rate_hz`, `sample_count`, `duration_s`,
`center_frequency_hz: 2400000000.0`, and an empty `"findings": []`.

Copy the `id` value from the response, then:

```bash
RECORDING_ID=<paste the id here>
curl -s http://localhost:8000/recordings/$RECORDING_ID | python3 -m json.tool
curl -s http://localhost:8000/recordings | python3 -m json.tool
curl -s http://localhost:8000/recordings/$RECORDING_ID/versions | python3 -m json.tool
```

These should return the same recording, show it in the catalogue list, and
show a one-entry version history.

**3. See validation actually reject something.** Prove the catalogue isn't
just accepting anything, by uploading a data object whose length doesn't
match a whole number of samples:

```python
# append to /tmp/upload_test_sigmf.py or run separately
s3.put_object(Bucket="rogue", Key="manual-check/bad.sigmf-meta", Body=json.dumps(meta).encode())
s3.put_object(Bucket="rogue", Key="manual-check/bad.sigmf-data", Body=samples[:-3])  # truncated
```

```bash
curl -s -X POST http://localhost:8000/recordings \
  -H "Content-Type: application/json" \
  -d '{
    "metadata_object_key": "manual-check/bad.sigmf-meta",
    "data_object_key": "manual-check/bad.sigmf-data"
  }' | python3 -m json.tool
```

Expect a `4xx` response body listing a `sigmf_data_length_mismatch` (or
`sigmf_checksum_mismatch`, since truncating also breaks the declared
`core:sha512`) finding, and nothing gets persisted for it.

**4. Look at the raw database row (optional).**

```bash
psql postgresql://rogue:rogue_dev_only@localhost:5432/rogue \
  -c "select id, version, access_classification, created_at from iq_recordings;"
```

You should see one row for the recording from step 2 (the rejected one from
step 3 won't appear — rejects are never written).

## M5 — RF spectrum planner

M5 is a single read-only endpoint,
`POST /scenarios/{id}/drafts/{id}/spectrum`, that computes deterministic
spectrum occupancy and conflict/headroom findings for a draft at one
scenario-time instant — nothing is persisted by calling it. This walkthrough
sets up a scenario/draft (M2), registers a synthetic recording (M4), attaches
three overlapping RF links to a mission, and calls the new endpoint.

**1. Scenario + draft** (same pattern as M2):

```bash
SCENARIO=$(curl -s -X POST http://localhost:8000/scenarios \
  -H "Content-Type: application/json" \
  -d '{
    "name": "manual-check spectrum scenario",
    "owner": "manual-check",
    "area_of_operation": {"type":"Polygon","coordinates":[[[13.0,52.0],[13.6,52.0],[13.6,52.6],[13.0,52.6],[13.0,52.0]]]}
  }')
SCENARIO_ID=$(echo "$SCENARIO" | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])")

DRAFT=$(curl -s -X POST http://localhost:8000/scenarios/$SCENARIO_ID/drafts \
  -H "Content-Type: application/json" -d '{"author":"manual-check"}')
DRAFT_ID=$(echo "$DRAFT" | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])")
```

**2. A synthetic recording** — reuses the same upload script as M4's
end-to-end section (run that section's `/tmp/upload_test_sigmf.py` first if
you haven't already):

```bash
RECORDING=$(curl -s -X POST http://localhost:8000/recordings \
  -H "Content-Type: application/json" \
  -d '{
    "metadata_object_key": "manual-check/test.sigmf-meta",
    "data_object_key": "manual-check/test.sigmf-data",
    "provenance": "manual check spectrum"
  }')
RECORDING_ID=$(echo "$RECORDING" | python3 -c "import sys,json;print(json.load(sys.stdin)['recording']['id'])")
```

That recording's `core:sample_rate` is 1 MHz — every occupied band below is
therefore ±500 kHz around its link's scripted frequency.

**3. Attach three RF links to a mission** — two comfortably inside their
declared band and 1 MHz apart (so their occupied bands overlap each other),
plus a third squeezed into a band far narrower than 1 MHz (so its occupied
band doesn't fit inside its own declared band):

```bash
curl -s -X PUT http://localhost:8000/scenarios/$SCENARIO_ID/drafts/$DRAFT_ID \
  -H "Content-Type: application/json" \
  -d '{
    "author": "manual-check",
    "expected_revision": 0,
    "zones": [], "receivers": [], "timeline_events": [],
    "recordings": [{"recording_id": "'"$RECORDING_ID"'", "version": 1}],
    "missions": [{
      "name": "recon-1",
      "platform": {"name": "Quad", "category": "multirotor", "max_speed_mps": 18.0},
      "trajectory": {
        "template": "waypoint_transit",
        "default_speed_mps": 12.0,
        "waypoints": [
          {"sequence_index": 0, "position": {"type": "Point", "coordinates": [13.4, 52.2]}, "altitude_m": 100.0},
          {"sequence_index": 1, "position": {"type": "Point", "coordinates": [13.45, 52.25]}, "altitude_m": 100.0}
        ]
      },
      "rf_links": [
        {
          "role": "c2",
          "band": {"freq_min_hz": 2.4e9, "freq_max_hz": 2.4835e9},
          "frequency_behaviour": {"mode": "scripted", "scripted_changes": [{"at_offset": "PT0S", "frequency_hz": 2.410e9}]},
          "emissions": [{"recording": {"recording_id": "'"$RECORDING_ID"'", "version": 1}}]
        },
        {
          "role": "video",
          "band": {"freq_min_hz": 2.4e9, "freq_max_hz": 2.4835e9},
          "frequency_behaviour": {"mode": "scripted", "scripted_changes": [{"at_offset": "PT0S", "frequency_hz": 2.4105e9}]},
          "emissions": [{"recording": {"recording_id": "'"$RECORDING_ID"'", "version": 1}}]
        },
        {
          "role": "telemetry",
          "band": {"freq_min_hz": 2.4100e9, "freq_max_hz": 2.4102e9},
          "frequency_behaviour": {"mode": "scripted", "scripted_changes": [{"at_offset": "PT0S", "frequency_hz": 2.4101e9}]},
          "emissions": [{"recording": {"recording_id": "'"$RECORDING_ID"'", "version": 1}}]
        }
      ]
    }]
  }' | python3 -m json.tool
```

**4. Call the spectrum endpoint:**

```bash
curl -s -X POST http://localhost:8000/scenarios/$SCENARIO_ID/drafts/$DRAFT_ID/spectrum \
  -H "Content-Type: application/json" -d '{"at_seconds": 0.0}' | python3 -m json.tool
```

Expect `"occupied_bands"` with 3 entries (one per link, each `bandwidth_hz:
1000000.0`) and `"findings"` with 4 entries: one `"bandwidth_exceeds_band"`
finding at `"severity": "blocking"` for the `telemetry` link (its declared
200 kHz band can't fit a 1 MHz-wide occupied band), and three
`"spectral_overlap"` findings at `"severity": "warning"` — one per pair of
links, since all three occupied bands overlap each other. Overlap is
reported, never rejected — CLAUDE.md's spectrum-planning rule 5 requires
intentional overlap to stay legal by default.

**5. See an idle link and an unresolved frequency mode (optional).** Change
`at_seconds` to something far in the future, or add a fourth link with
`"frequency_behaviour": {"mode": "mission_triggered", "mission_trigger_anchor": "waypoint:1"}`
and no `scripted_changes` — the mission-triggered link contributes no
occupied band and instead produces a `"frequency_unresolved"` warning
finding, since the backend has no mission-time-evaluation engine yet (that
logic is still frontend-only, M3's `missionEvaluator.ts`).

## Recording schedule + spectrum waterfall (supplemental)

Not one of CLAUDE.md's numbered M1–M14 milestones — added by direct request,
building on M1 (domain model) and M4 (catalogue). Three things to check:
a spectrogram overview computed once at ingest (not live per request),
signal-vs-background recording kind, and silence spans/overlap validation on
a `DroneRfLink`'s emissions.

### 1. A recording large enough to get a spectrogram overview

The overview needs at least 256 samples to compute even one FFT window (M4's
`test.sigmf-meta`/`test.sigmf-data` fixture above is only 100 — too short).
Upload a bigger synthetic one:

```python
# append to /tmp/upload_test_sigmf.py, or run standalone with the same s3 client setup
samples_big = b"".join(struct.pack("<ff", 0.001 * i, -0.001 * i) for i in range(2000))
meta_big = {
    "global": {"core:datatype": "cf32_le", "core:sample_rate": 1_000_000},
    "captures": [{"core:sample_start": 0, "core:frequency": 2_400_000_000}],
    "annotations": [],
}
s3.put_object(Bucket="rogue", Key="manual-check/overview.sigmf-meta", Body=json.dumps(meta_big).encode())
s3.put_object(Bucket="rogue", Key="manual-check/overview.sigmf-data", Body=samples_big)
print("uploaded manual-check/overview.sigmf-meta and manual-check/overview.sigmf-data")
```

Register it:

```bash
curl -s -X POST http://localhost:8000/recordings \
  -H "Content-Type: application/json" \
  -d '{
    "metadata_object_key": "manual-check/overview.sigmf-meta",
    "data_object_key": "manual-check/overview.sigmf-data",
    "provenance": "manual check overview"
  }' | python3 -m json.tool
```

Expect `"kind": "signal"` (the default) and a non-null `"overview_spectrogram"`
with 150 entries in `time_offsets_s`/`magnitude_db` and 256 in
`freq_offsets_hz` — computed once here, at ingest, not recomputed on every
later read of this recording.

### 2. A background-kind recording

```bash
curl -s -X POST http://localhost:8000/recordings \
  -H "Content-Type: application/json" \
  -d '{
    "metadata_object_key": "manual-check/overview.sigmf-meta",
    "data_object_key": "manual-check/overview.sigmf-data",
    "provenance": "manual check background",
    "kind": "background"
  }' | python3 -m json.tool
```

Expect `"kind": "background"` in the response — this is what
`RecordingPicker.tsx` groups/labels by in the editor, and what the frontend's
"only replay background data" scheduling choice actually selects.

### 3. Silence spans and overlap validation

Reuse the scenario/draft pattern from M5 section 1, and the recording from
step 1 above (`$RECORDING_ID`). Build a mission with one RF link carrying
three emissions: a signal span, a silence span (`"recording": null`, which
requires `duration_override`), and a third span placed to deliberately
overlap the first:

```bash
curl -s -X PUT http://localhost:8000/scenarios/$SCENARIO_ID/drafts/$DRAFT_ID \
  -H "Content-Type: application/json" \
  -d '{
    "author": "manual-check",
    "expected_revision": 0,
    "zones": [], "receivers": [], "timeline_events": [],
    "recordings": [{"recording_id": "'"$RECORDING_ID"'", "version": 1}],
    "missions": [{
      "name": "recon-1",
      "platform": {"name": "Quad", "category": "multirotor", "max_speed_mps": 18.0},
      "trajectory": {
        "template": "waypoint_transit",
        "default_speed_mps": 12.0,
        "waypoints": [
          {"sequence_index": 0, "position": {"type": "Point", "coordinates": [13.4, 52.2]}, "altitude_m": 100.0},
          {"sequence_index": 1, "position": {"type": "Point", "coordinates": [13.45, 52.25]}, "altitude_m": 100.0}
        ]
      },
      "rf_links": [{
        "role": "c2",
        "band": {"freq_min_hz": 2.4e9, "freq_max_hz": 2.4835e9},
        "frequency_behaviour": {"mode": "scripted", "scripted_changes": [{"at_offset": "PT0S", "frequency_hz": 2.410e9}]},
        "emissions": [
          {"recording": {"recording_id": "'"$RECORDING_ID"'", "version": 1}, "start_offset": "PT0S", "duration_override": "PT10S"},
          {"recording": null, "start_offset": "PT15S", "duration_override": "PT5S"},
          {"recording": {"recording_id": "'"$RECORDING_ID"'", "version": 1}, "start_offset": "PT5S", "duration_override": "PT10S"}
        ]
      }]
    }]
  }' | python3 -m json.tool

curl -s -X POST http://localhost:8000/scenarios/$SCENARIO_ID/drafts/$DRAFT_ID/validate | python3 -m json.tool
```

Expect the `PUT` to succeed (silence with an explicit duration is a valid
emission) and `validate` to return an `"overlapping_emissions"` BLOCKING
finding — the first (`0s`–`10s`) and third (`5s`–`15s`) emissions overlap by
5 seconds. Fix it by changing the third emission's `start_offset` to
`"PT10S"` (right after the first ends) and re-run `validate`: the finding
should disappear, leaving the silence span untouched in between.

### 4. In the editor UI

With the frontend dev server running (see the M3 section) and the same
scenario open:

1. Select the mission's RF link in the properties pane. Under **Emissions**,
   each row now has a **Silence** checkbox — checking it clears the
   recording picker and requires a duration (label changes to "Duration
   (required)"); unchecking it restores the picker.
2. The recording picker groups by platform as before, and now suffixes
   `· background` on any recording registered with `"kind": "background"`
   (step 2 above) so you can tell them apart from signal recordings at a
   glance.
3. Under **Resource preference (non-binding)**, check "Set a resource
   preference for this link" — tag/sync-class/notes fields appear. This is
   authored intent only; it never binds the link to a specific SDR (CLAUDE.md
   rule 1) — there's deliberately no device/serial field here.
4. In the timeline area below the map, a **Waterfall** panel renders per RF
   link: "No active emission" before the mission starts, "Silence — link is
   off-air" during the silence span you added, and a heatmap with a moving
   amber playhead once an emission with a computed overview is active. Play
   the timeline and confirm the playhead advances.

## M6 — Replay Plan compiler

M6 compiles a *published* `ScenarioVersion` (not a draft) into an immutable
`ReplayPlan`: realized frequency events, RF windows/composite channels and a
physical-channel allocation, against a declared/simulated
`HardwareCapabilityProfile` — never real, runtime-discovered hardware (that's
M8/M10). This walkthrough publishes a small scenario (M2) with one recording
(M4) and one RF link, then compiles it.

**1. Scenario, draft, recording** (same pattern as M5's setup):

```bash
SCENARIO=$(curl -s -X POST http://localhost:8000/scenarios \
  -H "Content-Type: application/json" \
  -d '{
    "name": "manual-check replay-plan scenario",
    "owner": "manual-check",
    "area_of_operation": {"type":"Polygon","coordinates":[[[13.0,52.0],[13.6,52.0],[13.6,52.6],[13.0,52.6],[13.0,52.0]]]}
  }')
SCENARIO_ID=$(echo "$SCENARIO" | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])")

DRAFT=$(curl -s -X POST http://localhost:8000/scenarios/$SCENARIO_ID/drafts \
  -H "Content-Type: application/json" -d '{"author":"manual-check"}')
DRAFT_ID=$(echo "$DRAFT" | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])")

RECORDING=$(curl -s -X POST http://localhost:8000/recordings \
  -H "Content-Type: application/json" \
  -d '{
    "metadata_object_key": "manual-check/test.sigmf-meta",
    "data_object_key": "manual-check/test.sigmf-data",
    "provenance": "manual check replay plan"
  }')
RECORDING_ID=$(echo "$RECORDING" | python3 -c "import sys,json;print(json.load(sys.stdin)['recording']['id'])")
```

**2. Attach one RF link, then publish** (compiling requires a *version*, not
a draft — this is the same publish call as M2):

```bash
curl -s -X PUT http://localhost:8000/scenarios/$SCENARIO_ID/drafts/$DRAFT_ID \
  -H "Content-Type: application/json" \
  -d '{
    "author": "manual-check",
    "expected_revision": 0,
    "zones": [], "receivers": [], "timeline_events": [],
    "missions": [{
      "name": "recon-1",
      "platform": {"name": "Quad", "category": "multirotor", "max_speed_mps": 18.0},
      "trajectory": {
        "template": "waypoint_transit",
        "default_speed_mps": 12.0,
        "waypoints": [
          {"sequence_index": 0, "position": {"type": "Point", "coordinates": [13.4, 52.2]}, "altitude_m": 100.0},
          {"sequence_index": 1, "position": {"type": "Point", "coordinates": [13.45, 52.25]}, "altitude_m": 100.0}
        ]
      },
      "rf_links": [{
        "role": "c2",
        "band": {"freq_min_hz": 2.4e9, "freq_max_hz": 2.4835e9},
        "frequency_behaviour": {"mode": "scripted", "scripted_changes": [{"at_offset": "PT0S", "frequency_hz": 2.412e9}]},
        "emissions": [{"recording": {"recording_id": "'"$RECORDING_ID"'", "version": 1}}]
      }]
    }]
  }' > /dev/null

VERSION=$(curl -s -X POST http://localhost:8000/scenarios/$SCENARIO_ID/drafts/$DRAFT_ID/publish)
VERSION_NUMBER=$(echo "$VERSION" | python3 -c "import sys,json;print(json.load(sys.stdin)['version_number'])")
```

**3. Compile it** (`duration_s` is the compile horizon — how far into the
scenario the plan covers, since there's no scenario-duration field yet;
`capability_profile` is omitted here, so it defaults to
`DEFAULT_CAPABILITY_PROFILE`, the illustrative 24-channel profile from
CLAUDE.md section 4):

```bash
PLAN=$(curl -s -X POST http://localhost:8000/scenarios/$SCENARIO_ID/versions/$VERSION_NUMBER/compile \
  -H "Content-Type: application/json" -d '{"duration_s": 20.0}')
PLAN_ID=$(echo "$PLAN" | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])")
echo "$PLAN" | python3 -m json.tool
```

Expect one `rf_windows` entry (the single link's occupied band, centered on
2.412 GHz) and one `allocations` entry pointing at an `x440-1` channel (the
first capability-profile channel whose tunable range covers 2.412 GHz),
`safety_policy_outcome.tx_authorized: false` (compiling never authorizes
transmission — that's M8), and `findings: []`. Keep `$SCENARIO_ID`/`$PLAN_ID`
around — the M7 section below continues from here.

**4. List/fetch the compiled plan:**

```bash
curl -s http://localhost:8000/scenarios/$SCENARIO_ID/replay-plans | python3 -m json.tool
```

**5. See a rejected compile (optional).** Re-run step 3 with a much smaller
`capability_profile` (e.g. one channel with `"max_usable_bandwidth_hz":
1000.0`) in the request body — the link's ~1 MHz occupied bandwidth no
longer fits any configured channel, so the response is `422` with a
`rf_window_infeasible` BLOCKING finding and nothing is persisted (check
step 4 again: the plan list is unchanged).

## M7 — Simulated SDR execution

M7 executes a compiled `ReplayPlan` (M6) through prepare → arm → start →
stop against an in-process simulated adapter — no real hardware, no
network, no separate Agent process (that's M8). This walkthrough continues
from the M6 section above: reuse its `$SCENARIO_ID`/`$PLAN_ID` if your
shell session still has them, or just re-run M6's steps 1-3 first.

**1. Create and prepare a run** (reserves every allocated channel,
verifies the plan's pinned recording hashes against the catalogue, then
preflights/configures each channel — all in one call):

```bash
RUN=$(curl -s -X POST http://localhost:8000/scenarios/$SCENARIO_ID/replay-plans/$PLAN_ID/runs \
  -H "Content-Type: application/json" -d '{"operator": "manual-check"}')
RUN_ID=$(echo "$RUN" | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])")
echo "$RUN" | python3 -m json.tool
```

Expect `"status": "prepared"` and three `events` (`reserved`,
`prefetch_verified`, `configured`) plus one `device_leases` entry per
allocated channel.

**2. Walk it through arm → start → stop**, checking the event list grows
(never shrinks) and the status advances at each step:

```bash
curl -s -X POST http://localhost:8000/scenarios/$SCENARIO_ID/replay-plans/$PLAN_ID/runs/$RUN_ID/arm \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['status'], len(d['events']))"

curl -s -X POST http://localhost:8000/scenarios/$SCENARIO_ID/replay-plans/$PLAN_ID/runs/$RUN_ID/start \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['status'], len(d['events']))"

curl -s -X POST http://localhost:8000/scenarios/$SCENARIO_ID/replay-plans/$PLAN_ID/runs/$RUN_ID/stop \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['status'], len(d['events']))"
```

Expect `armed 4`, `running 5`, `stopped 6` (exact counts depend on how many
channels the plan allocated — one channel in this setup).

**3. Confirm the run's evidence via `GET`:**

```bash
curl -s http://localhost:8000/scenarios/$SCENARIO_ID/replay-plans/$PLAN_ID/runs/$RUN_ID \
  | python3 -m json.tool
```

**4. Emergency-stop, from any state.** Create a second run and trigger
emergency-stop mid-`running` — this path takes no request body, is not
idempotency-key gated, and is always accepted (never 404s or 409s):

```bash
RUN2=$(curl -s -X POST http://localhost:8000/scenarios/$SCENARIO_ID/replay-plans/$PLAN_ID/runs \
  -H "Content-Type: application/json" -d '{"operator": "manual-check"}')
RUN2_ID=$(echo "$RUN2" | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])")

curl -s -X POST http://localhost:8000/scenarios/$SCENARIO_ID/replay-plans/$PLAN_ID/runs/$RUN2_ID/arm > /dev/null
curl -s -X POST http://localhost:8000/scenarios/$SCENARIO_ID/replay-plans/$PLAN_ID/runs/$RUN2_ID/start > /dev/null

curl -s -X POST http://localhost:8000/scenarios/$SCENARIO_ID/replay-plans/$PLAN_ID/runs/$RUN2_ID/emergency-stop \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['status'])"
```

Expect `emergency_stopped`.

**5. List every run for the plan:**

```bash
curl -s http://localhost:8000/scenarios/$SCENARIO_ID/replay-plans/$PLAN_ID/runs | python3 -m json.tool
```

Expect both runs from steps 1 and 4, in creation order.

## Real drone RF corpus loader (`scripts/ingest_drone_corpus.py`)

Everything above uses synthetic recordings. `scripts/ingest_drone_corpus.py`
is a small CLI tool that instead pulls real captures from a Droids-style
SigMF drone-RF dataset (one subdirectory per drone class, e.g.
`00`, `01`, ..., `no_drone`) and registers a representative sample through
the same M4 catalogue. Only relevant if you have such a dataset mounted
locally — e.g. `/media/cristian/Crucial X62/DroneIQRecordings/Droids_data11_sigmf/15June2022`.

**1. Preview the selection without touching anything:**

```bash
python scripts/ingest_drone_corpus.py \
  --source-root "/media/cristian/Crucial X62/DroneIQRecordings/Droids_data11_sigmf/15June2022" \
  --dry-run
```

Expect a list of one recording per drone-class subdirectory (drone id,
platform name pulled from the recording's own `classification:platform`
SigMF field, and which experiment scenario was picked — `air` preferred,
falling back to `los`/`env`/etc.) with a total size, and nothing uploaded.

**2. Run it for real** (needs the M0 server and section 0's Postgres/MinIO
running):

```bash
python scripts/ingest_drone_corpus.py \
  --source-root "/media/cristian/Crucial X62/DroneIQRecordings/Droids_data11_sigmf/15June2022"
```

Expect one `registered as <uuid> v1` line per drone class, streamed to MinIO
in 8MB chunks (never buffering a full ~32MB recording in memory) and ending
in `N/N ingested successfully`.

**Targeting a specific experiment/band instead of the default per-drone
pick:** pass `--scenario` and/or `--band` to filter on the SigMF filename's
`exp=`/`fc=` tokens (e.g. `--scenario both --band 5800e6` for "drone and
controller both transmitting, 5.8GHz" — only 4 of the 17 drone classes in
the 15June2022 campaign have a 5.8GHz recording at all, so this naturally
skips the rest with a `no matching SigMF recording under ...` note):

```bash
python scripts/ingest_drone_corpus.py \
  --source-root "/media/cristian/Crucial X62/DroneIQRecordings/Droids_data11_sigmf/15June2022" \
  --scenario both --band 5800e6 --dry-run
```

**3. Verify what landed:**

```bash
curl -s "http://localhost:8000/recordings?limit=50" | python3 -m json.tool
psql postgresql://rogue:rogue_dev_only@localhost:5432/rogue \
  -c "select id, version, provenance from iq_recordings where provenance like 'campaign=%' order by created_at;"
```

Each row's `provenance` string encodes the campaign, drone id and platform
(e.g. `campaign=15June2022, drone_id=00, platform=DJI Mavic 2 Pro, ...`), so
you can tell these apart from the synthetic M4 test data above at a glance.

**Note on reruns:** this is *not* idempotent — rerunning without deleting the
old rows first registers brand-new catalogue entries (duplicates), since no
`recording_id` is passed to update in place. If you're just re-verifying,
either accept the duplicates or delete the `iq_recordings` rows for that
campaign first (same `psql` pattern as above, with `delete from` instead of
`select`).

## Cleanup

- Stop the backend server with `Ctrl-C`; stop `frontend/dev.sh` with `Ctrl-C`
  in its terminal too.
- Everything created above (`manual-check scenario` in Postgres, the
  `manual-check/*` objects in MinIO, the `iq_recordings`/`replay_plans` rows)
  is harmless test data — delete it if you want a clean slate, or leave it;
  nothing in the app treats it specially.
- If you ran the drone corpus loader, its rows/objects are real reference
  data rather than throwaway test fixtures — worth keeping rather than
  deleting, unless you were just testing the script itself (see its "note on
  reruns" above).
