# Checking ROGUE yourself — manual verification guide (M0–M10, M11–M13 partial)

A hands-on walkthrough for verifying what's been built, without having to
read the code. Run each block from the repo root
(`/home/cristian/Programming/python/26.IC/rogue`).

**This guide was trimmed on 2026-09-08** — it had grown past 1400 lines and
several numbers (test counts, source-file counts) had drifted out of date as
milestones were added. If you're just trying to run the app, start with
**Quick start** below and stop there; the rest is milestone-by-milestone
verification detail for when you need to check a specific piece.

## Quick start: start, use, stop

**Start everything** (builds images the first time; add `--build` again
after pulling code changes):

```bash
docker compose up -d --build
```

This brings up Postgres, MinIO (+ its one-shot bucket-creation job), NATS,
the FastAPI backend, two simulated SDR Agents, the self-hosted map tiles
service, and the Vite frontend — the whole application, containerized.
Confirm it's actually healthy, not just started:

```bash
docker compose ps
```

`postgres`/`nats` should show `healthy`; `minio-init` should show `Exited
(0)` (it's a one-shot job — that's success, not a crash); everything else
`Up`. Then confirm the two layers that matter most:

```bash
curl -s http://localhost:8000/health          # backend: {"status":"ok","service":"rogue-api"}
curl -s http://localhost:8000/agents | python3 -c "
import sys, json
for a in json.load(sys.stdin): print(a['agent_id'], a['status'], len(a['capabilities']), 'channels')
"                                              # expect sim-agent-01/02, both 'online', 12 channels each
```

**Use it:** open **http://localhost:5173** in a browser. That's the whole
application:

- **Scenario Library** (`/`) — create/clone/list scenarios.
- **Scenario Development** (click **Edit** on a scenario) — the map,
  Spatial Knowledge (zones/missions/waypoints/receivers + a Doppler
  geometry sub-view), Signal Knowledge (RF links, spectrum preview,
  waterfalls) and the shared timeline scrub. Save/Validate/Publish are real
  calls to the backend, not local-only UI state.
- **Replay** (**Replay →** from the editor, or **Replay** from the
  library) — pick or compile a Replay Plan, create a run, and watch it:
  live drone position on the map, a waterfall grid per physical TX
  channel, the run's real watchdog/safety event feed, and Arm/Start/Stop/
  Emergency-stop controls.
- **SDR Console** (**SDR Console** from the library) — live inventory of
  registered Agents/devices/channels, with a manual refresh ("test
  connections").

Or skip the UI and hit the API directly: **http://localhost:8000/docs**
(interactive OpenAPI docs — every endpoint, "Try it out" fires a real
request against your running stack).

**Stop it:**

```bash
docker compose stop        # keeps all data (scenarios, recordings, runs) — pick this most of the time
docker compose down        # same, but also removes the containers (not the data volumes)
docker compose down -v     # full reset — also deletes Postgres/MinIO/NATS data. Everything you registered is gone.
```

**If you changed backend code and want a faster edit loop** than rebuilding
the `api` image every time, run the backend locally instead and let the
containers handle just the infra:

```bash
docker compose stop api                                  # free port 8000
source .venv/bin/activate
alembic upgrade head                                      # once, or after a new migration
uvicorn rogue.main:app --reload --app-dir backend          # local API, live-reloading
```

Same idea for the frontend — `docker compose stop ui` then `frontend/dev.sh`
instead of the containerized `ui`. `docker compose up -d api` (or `ui`)
hands the port back to the container when you're done.

## What's actually implemented

| Milestone | What it is | Status |
|---|---|---|
| M0 | Repo/CI shell, health endpoint | Done |
| M1 | Scenario domain model | Done |
| M2 | Scenario persistence & API | Done |
| M3 | Map + trajectory editor | Done — now split into a dedicated Development page (Spatial/Signal/Timeline) |
| M4 | SigMF recording catalogue | Done |
| M5 | RF spectrum planner | Done |
| M6 | Replay Plan compiler | Done |
| M7 | Simulated SDR execution | Done |
| M8 | Distributed SDR Agent | Done |
| M9 | First real adapter (Ettus X440) | Code complete, **hardware-unverified** (ADR-009) |
| M10 | X440 + AIR7311 capability-based scheduling | Live-scheduling: done. **AIR7311 hardware-verified 2026-09-08** (ADR-010, ADR-011). X440 hardware path still unverified. |
| M11–M13 (partial) | Multi-SDR sync / Doppler-delay-phase / TDOA-AOA stimulation | **Domain + compiler slice only**: coherent-group RF window generation and atomic channel allocation (ADR-012). Execution-layer (grouped lease/arm/start) and continuous per-sample DSP application are not built. |

Plus a UI overhaul (Replay page, SDR Console page, restructured Development
page) and a Replay/SDR Console frontend layer sitting on top of the above —
no new backend surface of its own.

## 0. One-time setup

```bash
cd /home/cristian/Programming/python/26.IC/rogue
source .venv/bin/activate
```

For anything below that talks to Postgres/MinIO directly (not through
`docker compose up`, i.e. running the backend with local `uvicorn`), start
just the infra services and apply migrations once:

```bash
docker compose up -d postgres minio minio-init nats
alembic upgrade head
```

**If you skip `alembic upgrade head` against a genuinely fresh Postgres
volume, the persistence/API tests below will fail (schema doesn't exist
yet) — this bites often enough to call out explicitly.**

Two gotchas, still current:

- **Port conflicts.** `api`/`ui` containers bind the same host ports
  (8000/5173) their local dev-server equivalents use. Running both at once
  gets you `[Errno 98] Address already in use` — `docker compose stop api`
  (or `ui`) frees the port, `docker compose up -d api` gives it back.
- **A stale local image** after a Node/dependency bump. If `docker compose
  build ui` fails with `EBADENGINE`, or `api` crashes on startup with a
  `pydantic_settings.exceptions.SettingsError`, that image predates a fix —
  `docker compose build <service>` picks up the current Dockerfile/code.
  Check what actually crashed with `docker compose logs api --tail 40`.

## Automated checks (covers all milestones)

The same checks CI/review runs, against a **fresh** DB with no Agents ever
registered against it (see the callout right after) — one shot at
everything:

```bash
ruff check backend tests agents
```
Expect `All checks passed!`

```bash
mypy backend/rogue && mypy agents
```
Expect `Success: no issues found in N source files` for each (71 and 8
respectively as of 2026-09-08 — the exact number drifts as files are
added; zero errors is the actual thing to check for).

```bash
pytest tests/unit -q
```
Expect **all passed, 0 failed** (358 as of 2026-09-08). If Postgres isn't
running or migrations haven't been applied, the persistence/API tests
error out instead of failing cleanly — that's section 0, not a code
problem.

**Known gotcha, worth knowing before you chase a false failure:** a handful
of tests (`tests/unit/persistence/test_agent_registry.py`,
`tests/unit/api/test_agents.py::test_list_agents_returns_seeded_presence`,
`tests/unit/persistence/test_replay.py::
test_compile_with_no_online_agents_falls_back_to_the_static_default`)
assume the `sdr_agents` table is completely empty. They are **not**
isolated from whatever Postgres instance you point them at — if you've
ever run `docker compose up` with the simulated Agents against this same
DB volume, their presence rows are still there (even stale ones still
count as "an agent exists" for these specific tests) and these tests will
fail. This is a real, pre-existing test-isolation gap, not something these
docs can fully paper over — if you hit exactly these failures and nothing
else, it's this, not a regression. Fix: run the test suite against a fresh
DB (`docker compose down -v && docker compose up -d postgres minio
minio-init nats && alembic upgrade head`) before ever starting a real or
simulated Agent against it.

To scope the run to one milestone:

```bash
pytest tests/unit/test_health.py -v                                                          # M0
pytest tests/unit/domain -v                                                                   # M1 + coherent-group domain additions
pytest tests/unit/persistence/test_repository.py tests/unit/api/test_scenarios.py -v          # M2
pytest tests/unit/catalogue tests/unit/persistence/test_catalogue.py tests/unit/api/test_recordings.py -v   # M4 + recording schedule/waterfall
pytest tests/unit/spectrum tests/unit/persistence/test_spectrum.py tests/unit/api/test_spectrum_planner.py -v   # M5
pytest tests/unit/compiler tests/unit/persistence/test_replay.py tests/unit/api/test_replay_compiler.py -v   # M6 + coherent-group compiler additions
pytest tests/unit/domain/test_run.py tests/unit/execution tests/unit/persistence/test_run_execution.py tests/unit/api/test_runs.py -v   # M7
pytest tests/unit/agents tests/unit/protocol tests/unit/persistence/test_agent_registry.py tests/unit/persistence/test_lease_sweep.py tests/unit/execution/test_remote_adapter.py tests/unit/execution/test_distributed_integration.py tests/unit/api/test_agents.py -v   # M8/M9/M10
pytest tests/unit/domain/test_geometry.py tests/unit/domain/test_mission_evaluator.py tests/unit/compiler/test_coherent_groups.py -v   # M11-M13 (partial) new modules
```

Frontend checks, from `frontend/`:

```bash
npm run typecheck
npm test          # 143 tests as of 2026-09-08
npm run lint      # oxlint
npm run format:check   # prettier
npm run e2e       # needs the backend + frontend dev servers running
```

The rest of this guide is about *seeing specific things work*, one
milestone at a time — skip to whichever you care about.

## Common setup used by several sections below

M5, M6, M8, M9 and M10 all need the same three things first: a scenario, a
draft on it, and a registered recording. Rather than repeat this in every
section, do it once here and reuse `$SCENARIO_ID`/`$DRAFT_ID`/
`$RECORDING_ID` (or re-run this block per section if you want independent
scenarios — either works, nothing below depends on a specific name).

**A synthetic SigMF recording**, uploaded straight to MinIO (a real capture
isn't needed — the catalogue only cares the two objects exist and are
internally consistent):

```python
# save as /tmp/upload_test_sigmf.py
import hashlib, json, struct
import boto3

samples = b"".join(struct.pack("<ff", 0.001 * i, -0.001 * i) for i in range(100))
meta = {
    "global": {"core:datatype": "cf32_le", "core:sample_rate": 1_000_000,
               "core:sha512": hashlib.sha512(samples).hexdigest()},
    "captures": [{"core:sample_start": 0, "core:frequency": 2_400_000_000}],
    "annotations": [],
}
s3 = boto3.client("s3", endpoint_url="http://localhost:9000",
                   aws_access_key_id="rogue", aws_secret_access_key="rogue_dev_password")
s3.put_object(Bucket="rogue", Key="manual-check/test.sigmf-meta", Body=json.dumps(meta).encode())
s3.put_object(Bucket="rogue", Key="manual-check/test.sigmf-data", Body=samples)
print("uploaded manual-check/test.sigmf-meta and manual-check/test.sigmf-data")
```

```bash
python /tmp/upload_test_sigmf.py
```

**Scenario + draft + registered recording:**

```bash
SCENARIO=$(curl -s -X POST http://localhost:8000/scenarios \
  -H "Content-Type: application/json" \
  -d '{"name":"manual-check scenario","owner":"manual-check",
       "area_of_operation":{"type":"Polygon","coordinates":[[[13.0,52.0],[13.6,52.0],[13.6,52.6],[13.0,52.6],[13.0,52.0]]]}}')
SCENARIO_ID=$(echo "$SCENARIO" | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])")

DRAFT=$(curl -s -X POST http://localhost:8000/scenarios/$SCENARIO_ID/drafts \
  -H "Content-Type: application/json" -d '{"author":"manual-check"}')
DRAFT_ID=$(echo "$DRAFT" | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])")

RECORDING=$(curl -s -X POST http://localhost:8000/recordings \
  -H "Content-Type: application/json" \
  -d '{"metadata_object_key":"manual-check/test.sigmf-meta","data_object_key":"manual-check/test.sigmf-data","provenance":"manual check"}')
RECORDING_ID=$(echo "$RECORDING" | python3 -c "import sys,json;print(json.load(sys.stdin)['recording']['id'])")
```

That recording's `core:sample_rate` is 1 MHz, so any RF link scheduled on
it occupies ~1 MHz centered on its scripted frequency.

## M0 — repository shell & health check

```bash
uvicorn rogue.main:app --reload --app-dir backend
```
```bash
curl -s http://localhost:8000/health -w "\nHTTP %{http_code}\n"
```
Expect `{"status":"ok","service":"rogue-api"}` and `HTTP 200`. Leave it
running — every curl-based section below uses it (or use the containerized
`api` from Quick Start instead; both work identically).

## M1 — scenario domain model

No HTTP surface — the typed Pydantic schema everything else is built on
(`backend/rogue/domain/`), proven by round-tripping the example scenario:

```bash
PYTHONPATH=backend python3 - <<'EOF'
from rogue.domain.scenario import ScenarioVersion
from rogue.domain.serialization import from_yaml, to_yaml
from rogue.domain.validation import validate_scenario_version

text = open("examples/scenarios/single-drone-orbit.yaml").read()
version = from_yaml(ScenarioVersion, text)
print("parsed:", version.scenario_id, "version", version.version_number)
print("missions:", [m.name for m in version.missions])
print("validation findings:", validate_scenario_version(version))
print("round-trip equal:", from_yaml(ScenarioVersion, to_yaml(version)) == version)
EOF
```
Expect one mission (`recon-1`), an empty findings list, `round-trip equal:
True`.

## M2 — scenario persistence & API

With a server running (M0):

```bash
curl -s -X POST http://localhost:8000/scenarios/$SCENARIO_ID/drafts/$DRAFT_ID/validate | python3 -m json.tool
curl -s -X POST http://localhost:8000/scenarios/$SCENARIO_ID/drafts/$DRAFT_ID/publish | python3 -m json.tool
curl -s http://localhost:8000/scenarios/$SCENARIO_ID/versions/1 | python3 -m json.tool
```

(Uses the scenario/draft from **Common setup** above.) Expect `validate` to
return one `"warning"`-severity `empty_scenario` finding (an empty scenario
is legal, just noteworthy); `publish` returns `version_number: 1` carrying
that finding; `GET .../versions/1` returns the same, now-immutable version.

## M3 — Scenario Development page

Frontend feature — click through a browser. See **Quick start** above for
starting the frontend; **http://localhost:5173** either way.

**Self-hosted basemap (optional, one-time):** without it, the map falls
back to a flat offline color — every behavior below still works, you just
won't see real streets.

```bash
scripts/build_map_tiles.sh          # downloads a Berlin OSM extract, ~1.4GB combined, cached after first run
docker compose up -d tiles
curl -s http://localhost:8081/styles/basic-preview/style.json | python3 -m json.tool | head -20   # confirm real vector sources, not a flat fallback
```

**Walkthrough:**

1. Open the library, click **Edit** on `manual-check scenario`. You should
   see the map, a **Spatial Knowledge** column (Objects/Doppler tabs;
   Zones/Missions/Receivers lists) on the right of it, a full-width
   **Signal Knowledge** row (RF links table, spectrum preview, waterfalls)
   below that, and a Timeline scrub strip at the bottom.
2. Click **+ Mission** — a drone with a default 2-waypoint trajectory
   appears; header shows `revision 0 · unsaved changes`.
3. Click **Save** → `revision 1 · saved` (a real `PUT` with optimistic
   concurrency, not local UI state — refresh the page to confirm the
   mission survived).
4. Click **Validate**, then **Publish** — back in the library, "Current
   version" should now say `published`.
5. Click **Play** on the timeline — the drone position on the map should
   advance with it.
6. Add a receiver (**+ Receiver**), switch Spatial Knowledge to the
   **Doppler** tab — you should see range/range-rate for each
   receiver×mission pair at the current scrub time.
7. Click **Replay →** in the header — this takes you to the Replay Plans
   chooser for this scenario (M6/M7 territory; see those sections for what
   to expect there once you have a compiled plan).

Automated checks: `npm run typecheck`, `npm test`, `npm run e2e` (see
**Automated checks** above).

## M4 — SigMF recording catalogue

**Browse the API:** http://localhost:8000/docs → `recordings` section —
`POST`/`GET /recordings`, `GET /recordings/{id}`, `GET
/recordings/{id}/versions`. "Try it out" fires real requests.

**End-to-end** (the recording from **Common setup** above already exercised
register → fetch; this adds the negative case):

```bash
curl -s http://localhost:8000/recordings/$RECORDING_ID | python3 -m json.tool
curl -s http://localhost:8000/recordings | python3 -m json.tool
curl -s http://localhost:8000/recordings/$RECORDING_ID/versions | python3 -m json.tool
```

**See validation actually reject something** — upload a data object whose
length doesn't match a whole sample count:

```python
# append to /tmp/upload_test_sigmf.py, or run standalone
s3.put_object(Bucket="rogue", Key="manual-check/bad.sigmf-meta", Body=json.dumps(meta).encode())
s3.put_object(Bucket="rogue", Key="manual-check/bad.sigmf-data", Body=samples[:-3])  # truncated
```
```bash
curl -s -X POST http://localhost:8000/recordings \
  -H "Content-Type: application/json" \
  -d '{"metadata_object_key":"manual-check/bad.sigmf-meta","data_object_key":"manual-check/bad.sigmf-data"}' \
  | python3 -m json.tool
```
Expect a `4xx` with a `sigmf_data_length_mismatch` (or
`sigmf_checksum_mismatch`) finding; nothing gets persisted.

**Raw DB row (optional):**
```bash
psql postgresql://rogue:rogue_dev_only@localhost:5432/rogue \
  -c "select id, version, access_classification, created_at from iq_recordings;"
```

### Recording schedule + spectrum waterfall (supplemental — not a numbered milestone)

Builds on M1+M4: a spectrogram overview computed once at ingest, signal-vs-
background recording kind, silence spans/overlap validation.

**A recording big enough for a spectrogram overview** (256+ samples;
`test.sigmf-data` above is only 100):

```python
samples_big = b"".join(struct.pack("<ff", 0.001 * i, -0.001 * i) for i in range(2000))
meta_big = {"global": {"core:datatype": "cf32_le", "core:sample_rate": 1_000_000},
            "captures": [{"core:sample_start": 0, "core:frequency": 2_400_000_000}], "annotations": []}
s3.put_object(Bucket="rogue", Key="manual-check/overview.sigmf-meta", Body=json.dumps(meta_big).encode())
s3.put_object(Bucket="rogue", Key="manual-check/overview.sigmf-data", Body=samples_big)
```
```bash
curl -s -X POST http://localhost:8000/recordings \
  -H "Content-Type: application/json" \
  -d '{"metadata_object_key":"manual-check/overview.sigmf-meta","data_object_key":"manual-check/overview.sigmf-data","provenance":"manual check overview"}' \
  | python3 -m json.tool
```
Expect `"kind": "signal"` and a non-null `overview_spectrogram` (150
time bins × 256 freq bins) — computed once here, not recomputed on later
reads.

**Background-kind** (add `"kind": "background"` to the same POST body) —
expect it echoed back; this is what `RecordingPicker.tsx` groups by.

**Silence + overlap** — attach one RF link with a signal span, a silence
span (`"recording": null`, requires `duration_override`), and a third span
overlapping the first, then `validate` the draft: expect an
`overlapping_emissions` BLOCKING finding. Fix the overlap and re-validate —
finding disappears, silence span untouched. (Full request body: see git
history of this file, or build it interactively in the editor — Emissions
rows have a **Silence** checkbox that does the same thing.)

**In the editor UI:** select an RF link → Emissions rows show the Silence
checkbox; the recording picker suffixes `· background` on background-kind
recordings; the Waterfall panel under the map shows "No active emission" /
"Silence — link is off-air" / a heatmap with a moving playhead depending on
scrub position.

## M5 — RF spectrum planner

Single read-only endpoint, `POST /scenarios/{id}/drafts/{id}/spectrum` —
computes deterministic occupancy/conflict findings at one instant, nothing
persisted.

**Three overlapping RF links** (two 1 MHz apart inside their declared band,
a third squeezed into a band too narrow for its own occupied bandwidth):

```bash
curl -s -X PUT http://localhost:8000/scenarios/$SCENARIO_ID/drafts/$DRAFT_ID \
  -H "Content-Type: application/json" \
  -d '{
    "author": "manual-check", "expected_revision": 0,
    "zones": [], "receivers": [], "timeline_events": [],
    "recordings": [{"recording_id": "'"$RECORDING_ID"'", "version": 1}],
    "missions": [{
      "name": "recon-1",
      "platform": {"name": "Quad", "category": "multirotor", "max_speed_mps": 18.0},
      "trajectory": {"template": "waypoint_transit", "default_speed_mps": 12.0, "waypoints": [
        {"sequence_index": 0, "position": {"type": "Point", "coordinates": [13.4, 52.2]}, "altitude_m": 100.0},
        {"sequence_index": 1, "position": {"type": "Point", "coordinates": [13.45, 52.25]}, "altitude_m": 100.0}
      ]},
      "rf_links": [
        {"role": "c2", "band": {"freq_min_hz": 2.4e9, "freq_max_hz": 2.4835e9},
         "frequency_behaviour": {"mode": "scripted", "scripted_changes": [{"at_offset": "PT0S", "frequency_hz": 2.410e9}]},
         "emissions": [{"recording": {"recording_id": "'"$RECORDING_ID"'", "version": 1}}]},
        {"role": "video", "band": {"freq_min_hz": 2.4e9, "freq_max_hz": 2.4835e9},
         "frequency_behaviour": {"mode": "scripted", "scripted_changes": [{"at_offset": "PT0S", "frequency_hz": 2.4105e9}]},
         "emissions": [{"recording": {"recording_id": "'"$RECORDING_ID"'", "version": 1}}]},
        {"role": "telemetry", "band": {"freq_min_hz": 2.4100e9, "freq_max_hz": 2.4102e9},
         "frequency_behaviour": {"mode": "scripted", "scripted_changes": [{"at_offset": "PT0S", "frequency_hz": 2.4101e9}]},
         "emissions": [{"recording": {"recording_id": "'"$RECORDING_ID"'", "version": 1}}]}
      ]
    }]
  }' > /dev/null

curl -s -X POST http://localhost:8000/scenarios/$SCENARIO_ID/drafts/$DRAFT_ID/spectrum \
  -H "Content-Type: application/json" -d '{"at_seconds": 0.0}' | python3 -m json.tool
```

Expect 3 `occupied_bands` (each `bandwidth_hz: 1000000.0`) and 4 findings:
one `bandwidth_exceeds_band` BLOCKING (telemetry's 200 kHz band can't fit a
1 MHz occupied band) and three `spectral_overlap` WARNINGs (every pair of
the three overlaps). Overlap is reported, never rejected — CLAUDE.md rule 5
requires intentional overlap to stay legal by default.

## M6 — Replay Plan compiler

Compiles a *published* `ScenarioVersion` into an immutable `ReplayPlan`
against a declared/simulated (or, per M10, live-discovered) capability
profile.

```bash
VERSION=$(curl -s -X POST http://localhost:8000/scenarios/$SCENARIO_ID/drafts/$DRAFT_ID/publish)
VERSION_NUMBER=$(echo "$VERSION" | python3 -c "import sys,json;print(json.load(sys.stdin)['version_number'])")

PLAN=$(curl -s -X POST http://localhost:8000/scenarios/$SCENARIO_ID/versions/$VERSION_NUMBER/compile \
  -H "Content-Type: application/json" -d '{"duration_s": 20.0}')
PLAN_ID=$(echo "$PLAN" | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])")
echo "$PLAN" | python3 -m json.tool
```

(Uses the RF links from the M5 draft above — 3 links → 3 `rf_windows`/
`allocations`, since none of them share `array_group_id`.) `duration_s` is
the compile horizon. No explicit `capability_profile` → defaults to
`live-agent-registry` if any Agent is online (M10), else the static
`default-initial-planning-profile` (24 illustrative channels). Expect
`safety_policy_outcome.tx_authorized: false` always — compiling never
authorizes transmission (that's execution, M7+).

**Rejected compile (optional):** re-run with a tiny `capability_profile`
(e.g. one channel, `"max_usable_bandwidth_hz": 1000.0`) — expect `422` with
`rf_window_infeasible`, nothing persisted.

## M7 — Simulated SDR execution

Prepare → arm → start → stop against an in-process simulated adapter — no
real hardware, no network.

```bash
RUN=$(curl -s -X POST http://localhost:8000/scenarios/$SCENARIO_ID/replay-plans/$PLAN_ID/runs \
  -H "Content-Type: application/json" -d '{"operator": "manual-check"}')
RUN_ID=$(echo "$RUN" | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])")
echo "$RUN" | python3 -m json.tool   # expect "prepared", 3 events (reserved/prefetch_verified/configured)

curl -s -X POST http://localhost:8000/scenarios/$SCENARIO_ID/replay-plans/$PLAN_ID/runs/$RUN_ID/arm \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['status'], len(d['events']))"
curl -s -X POST http://localhost:8000/scenarios/$SCENARIO_ID/replay-plans/$PLAN_ID/runs/$RUN_ID/start \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['status'], len(d['events']))"
curl -s -X POST http://localhost:8000/scenarios/$SCENARIO_ID/replay-plans/$PLAN_ID/runs/$RUN_ID/stop \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['status'], len(d['events']))"
```
Expect the status to advance and the event count to only ever grow.

**Emergency-stop from any state** — no request body, not idempotency-key
gated, always accepted:
```bash
curl -s -X POST http://localhost:8000/scenarios/$SCENARIO_ID/replay-plans/$PLAN_ID/runs/$RUN_ID/emergency-stop \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['status'])"
```

**Or drive this from the UI instead:** go to the scenario's **Replay →**
page, use **Create run** on the compiled plan, then Arm/Start/Stop from the
Replay page's controls — the map shows the drone's live position (driven
by run time, not the authoring scrub) and a waterfall tile per physical
channel.

## M8 — Distributed SDR Agent

M7's in-process adapter replaced by real, separate Agent processes over
NATS (still simulated hardware — ADR-008). Use the full `docker compose up
-d --build` stack from **Quick start**, not local `uvicorn`.

**Confirm both Agents, compile against them, run it:**
```bash
curl -s http://localhost:8000/agents | python3 -c "
import sys, json
for a in json.load(sys.stdin): print(a['agent_id'], a['status'], len(a['capabilities']))
"
```
Expect `sim-agent-01`/`sim-agent-02`, `online`, 12 capabilities each. Then
repeat M6/M7 above against the containerized API (`localhost:8000` is the
same either way) — the allocation should land on `x440-1` or `air7311-1`
(owned by `sim-agent-01`), and `docker compose logs simulated-agent-1
--tail=5` should show a real cache-download line once you create+prepare a
run (M7 only re-checked a stored hash; M8 actually caches bytes).

**Lease renewal, unattended:**
```bash
sleep 12
curl -s http://localhost:8000/scenarios/$SCENARIO_ID/replay-plans/$PLAN_ID/runs/$RUN_ID \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['device_leases'][0]['expires_at'], [e['kind'] for e in d['events']])"
```
Expect at least one `lease_renewed` event (runs on a ~10s interval purely
from the API's background task).

**Kill the owning Agent mid-run:**
```bash
docker compose stop simulated-agent-1
sleep 20
curl -s http://localhost:8000/scenarios/$SCENARIO_ID/replay-plans/$PLAN_ID/runs/$RUN_ID \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['status']); [print(e['kind'], e['message']) for e in d['events'][-2:]]"
```
Expect `emergency_stopped` — the central lease sweep reaches a safe
terminal state even though the physical stop command can't reach a dead
process.

```bash
docker compose start simulated-agent-1
```
brings it back and it re-registers within a few seconds.

## M9 — First real adapter (Ettus X440)

**Unverified — no UHD install or physical X440 available in the dev
environment this was built in.** ADR-009 records this explicitly.
`EttusX440Adapter`'s command sequencing, real-TX safety gate and bounded-
chunk streaming are covered by `pytest tests/unit/agents/test_x440_adapter.py`
against a fake `UHDDevice`; the actual hardware path needs you to run this
in a lab.

**Safety first.** `ROGUE_ENABLE_REAL_TX=1` is a real transmit-enable switch
(CLAUDE.md rule 12). Never point this at an antenna — cabled/attenuated
only: X440 TX → fixed attenuator (sized to your analyzer/receiver's safe
input level) → spectrum analyzer or a second SDR as receiver.

```bash
pip install .[x440]
python -c "import uhd; print(uhd.__version__)"    # must succeed before anything below will
uhd_find_devices
```

Confirm `agents/common/x440_adapter.py`'s UHD calls (`MultiUSRP`,
`StreamArgs`, `TuneRequest`, `TXMetadata`) against your installed version —
written against documented UHD API, not exercised against a real install:
```python
import uhd
usrp = uhd.usrp.MultiUSRP("addr=<your X440's address>")
print(usrp.get_tx_num_channels())
print(usrp.get_tx_freq_range(0))
```
Adjust the adapter if anything doesn't match, re-run
`pytest tests/unit/agents/test_x440_adapter.py`.

Then: register a real `cf32_le` recording, compile a plan (M6, stop before
creating a run), start the Agent —
```bash
ROGUE_AGENT_ID=x440-lab-01 ROGUE_AGENT_MODE=x440 ROGUE_AGENT_DEVICE_IDS=x440-1 \
ROGUE_X440_DEVICE_ARGS="addr=<your X440's address>" ROGUE_ENABLE_REAL_TX=1 \
ROGUE_NATS_URL=nats://<control-server>:4222 \
ROGUE_S3_ENDPOINT=http://<control-server>:9000 \
ROGUE_S3_ACCESS_KEY=rogue ROGUE_S3_SECRET_KEY=rogue_dev_password \
python -m agents.common.main
```
— confirm it registers with real device-discovered capabilities (not the
static default), create+arm+start a run and watch the analyzer, confirm
`stop`/`emergency-stop` actually cease transmission, and confirm `start`
fails with `ROGUE_ENABLE_REAL_TX` unset. Report back anything that needed
adjusting.

## M10 — AIR7311 adapter + live capability-based scheduling

**Part A — live scheduling** (needs no special hardware, just Agents
online): covered above in M6/M8 — compiling with no explicit
`capability_profile` picks up `live-agent-registry` once an Agent is
online, and falls back to the static default once none are (stop both
simulated Agents, wait ~20s past their presence-staleness window, recompile
and confirm `capability_profile.id == "default-initial-planning-profile"`).

**Part B — DeepwaveAIR7311Adapter: hardware-verified 2026-09-08.** Full
detail, exact device args, and the caveat about the lab unit's Python 3.10
SoapySDR bindings (worked around via a temporary, narrowly-scoped
SoapyRemote exception) are in **ADR-011** — not repeated here. Summary: a
real AIR7311 registered live, the compiler scheduled against it, and a full
`reserve→prefetch_verified→configure→arm→start→stop` cycle ran real,
40 dB-attenuated TX, correctly refusing to start with `ROGUE_ENABLE_REAL_TX`
unset. If you're setting this up yourself:

```bash
SoapySDRUtil --find     # confirm `driver = SoapyAIRT` — the exact value ROGUE_AIR7311_DEVICE_ARGS needs
```
```bash
ROGUE_AGENT_ID=air7311-orin-01 ROGUE_AGENT_MODE=air7311 ROGUE_AGENT_DEVICE_IDS=air7311-1 \
ROGUE_AIR7311_DEVICE_ARGS="driver=SoapyAIRT" ROGUE_ENABLE_REAL_TX=0 \
ROGUE_NATS_URL=nats://<control-server>:4222 \
ROGUE_S3_ENDPOINT=http://<control-server>:9000 \
ROGUE_S3_ACCESS_KEY=rogue ROGUE_S3_SECRET_KEY=rogue_dev_password \
python -m agents.common.main
```
(If your Agent host is still Python 3.10 like the unit ADR-011 documents,
see that ADR for the SoapyRemote workaround device-args instead.) Same
cabled/attenuated safety setup as M9; same `ROGUE_ENABLE_REAL_TX=0` first,
confirm presence/`discover()`/`configure`, then `1`.

## M11–M13 (partial) — coherent-group RF window generation

Domain + compiler slice only (ADR-012) — no execution/orchestrator/NATS/
agent changes, so nothing here needs real or simulated hardware to verify:

```bash
pytest tests/unit/domain/test_geometry.py tests/unit/domain/test_mission_evaluator.py \
       tests/unit/compiler/test_coherent_groups.py tests/unit/compiler/test_windows.py \
       tests/unit/compiler/test_allocation.py tests/unit/compiler/test_compile.py -v
```

To see it end to end: publish a scenario with one `DroneRfLink` carrying an
`array_group_id`, plus 2+ `Receiver`s (type `tdoa` or `aoa_doa`) sharing
that same `array_group_id`, then compile it (M6 above) — expect **N
separate `rf_windows`** (one per receiver element, never merged even
though they're frequency-identical) each with exactly one
`CompositeChannel` carrying a non-null `coherent_group_id`,
`array_element_receiver_id`, and a computed `delay_offset_s` (plus
`phase_offset_rad` for `aoa_doa` elements), and **N allocations landing on N
distinct physical channels** — or, if not enough channels are free, **zero**
allocations for the whole group plus one
`insufficient_physical_channels_for_coherent_group` finding (atomic, not
partial).

## Real drone RF corpus loader (`scripts/ingest_drone_corpus.py`)

Everything above uses synthetic recordings. This CLI instead pulls real
captures from a Droids-style SigMF drone-RF dataset (one subdirectory per
drone class) and registers a representative sample through the M4
catalogue. Only relevant if you have such a dataset mounted locally.

```bash
python scripts/ingest_drone_corpus.py --source-root "<path-to-dataset>" --dry-run     # preview, nothing uploaded
python scripts/ingest_drone_corpus.py --source-root "<path-to-dataset>"               # for real, streamed in 8MB chunks
```

Filter with `--scenario`/`--band` (e.g. `--scenario both --band 5800e6`).
Verify what landed:
```bash
curl -s "http://localhost:8000/recordings?limit=50" | python3 -m json.tool
psql postgresql://rogue:rogue_dev_only@localhost:5432/rogue \
  -c "select id, version, provenance from iq_recordings where provenance like 'campaign=%' order by created_at;"
```

**Not idempotent** — rerunning without deleting old rows first creates
duplicates (no `recording_id` is passed to update in place).

## Cleanup

- `docker compose stop` (keep data) or `docker compose down -v` (full
  reset — see **Quick start**).
- If you ran things locally instead: `Ctrl-C` the `uvicorn`/`frontend/
  dev.sh` processes.
- Everything under `manual-check*` (scenario names, MinIO keys, DB rows) is
  harmless test data — delete it or leave it, nothing treats it specially.
- Drone-corpus-loader rows are real reference data, not throwaway fixtures
  — worth keeping unless you were just testing the script itself.
