# Checking ROGUE yourself — manual verification guide (M0–M4)

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
| — | Real drone RF corpus loader (`scripts/ingest_drone_corpus.py`) | run the script, then `curl`/`psql` |

Each section is independent — jump to whichever milestone you want to check.
Section 0 is shared setup everything else depends on.

## 0. One-time setup

```bash
cd /home/cristian/Programming/python/26.IC/rogue
source .venv/bin/activate
```

M2/M3/M4 need Postgres and MinIO (S3-compatible storage) running locally.
M0/M1 don't need anything beyond the venv. Check whether the services are up:

```bash
docker ps --filter "name=rogue-postgres" --filter "name=rogue-minio"
```

If that prints nothing, start them:

```bash
docker-compose up -d postgres minio minio-init
```

(If `docker-compose up` errors with `KeyError: 'ContainerConfig'`, the
containers exist but are stale — find them with `docker ps -a --filter
name=rogue` and start them by container ID instead, e.g. `docker start
<postgres_id> <minio_id>`.)

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
Expect: `Success: no issues found in 35 source files`

```bash
pytest tests/unit -q
```
Expect: `127 passed`. (If Postgres isn't running, the persistence/API tests
will error out with a connection-refused message — that's the DB, not a
code problem; go back to section 0.)

To scope the test run to one milestone:

```bash
pytest tests/unit/test_health.py -v                                  # M0
pytest tests/unit/domain -v                                          # M1
pytest tests/unit/persistence/test_repository.py tests/unit/api/test_scenarios.py -v   # M2
pytest tests/unit/catalogue tests/unit/persistence/test_catalogue.py tests/unit/api/test_recordings.py -v   # M4
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
  `manual-check/*` objects in MinIO, the `iq_recordings` row) is harmless
  test data — delete it if you want a clean slate, or leave it; nothing in
  the app treats it specially.
- If you ran the drone corpus loader, its rows/objects are real reference
  data rather than throwaway test fixtures — worth keeping rather than
  deleting, unless you were just testing the script itself (see its "note on
  reruns" above).
