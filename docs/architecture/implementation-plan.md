# ROGUE Implementation Plan

## 1. Development strategy

Build ROGUE in bounded, testable increments. Do not begin with hardware-specific replay. Establish scenario semantics, schemas, Replay Plan and simulation first.

## 2. Recommended sequence

| Milestone | Deliverable | Exit criterion | Status |
|---|---|---|---|
| M0 | Repository, architecture docs, CI, Compose, UI/API shell, simulated agent | one-command local environment and health tests | Done |
| M1 | Scenario domain model | typed/versioned scenario round-trip with tests | Done — `backend/rogue/domain/`, merged to `develop` |
| M2 | Scenario persistence/API | draft/version/clone/validation APIs | Done — `feature/scenario-persistence-api`, merged to `develop` |
| M3 | Map + trajectory editor | multi-drone scenario visual playback | Done — `feature/map-trajectory-editor`, merged to `develop` |
| M4 | SigMF catalogue | validated immutable recording assets | In progress — `feature/sigmf-catalogue` |
| M5 | RF spectrum planner | deterministic spectrum state and conflict/headroom findings | Planned |
| M6 | Replay Plan compiler | scenario compiles to hardware-neutral executable plan | Planned |
| M7 | Simulated SDR execution | full prepare/arm/start/stop without hardware | Planned |
| M8 | Distributed SDR Agent | leases, cache, protocol, watchdog, telemetry | Planned |
| M9 | First real adapter | cabled/attenuated replay on one supported device | Planned |
| M10 | X440 + AIR7311 capability-based scheduling | both hardware families behind common interface | Planned |
| M11 | Multi-SDR synchronization | declared timing class demonstrated and measured | Planned |
| M12 | Doppler/delay/phase processing | receiver-specific streams validated | Planned |
| M13 | TDOA/AOA receiver stimulation | relative delay/phase requirements demonstrated | Planned |
| M14 | Independent RF validation | measured RF evidence attached to run | Planned |

## 3. Feature sequence

### M1 — Scenario domain model (done)

Implemented in `feature/scenario-domain-model` (merged to `develop`): typed models, validation,
YAML/JSON serialization and schemas for Scenario, Timeline, Platform/Drone, Trajectory/Waypoint,
RF links/emissions/frequency events, recording references, receivers and hardware resource
constraints, under `backend/rogue/domain/` with tests in `tests/unit/domain/` and an example
scenario at `examples/scenarios/single-drone-orbit.yaml`. `ScenarioRun`/Replay Plan were
intentionally not modelled (M6+). SDR control was not implemented in this feature.

### M2 — Scenario persistence/API (done)

Implemented in `feature/scenario-persistence-api` (merged to `develop`). Persists
`Scenario`/`ScenarioDraft`/`ScenarioVersion` (SQLAlchemy 2 + PostgreSQL/PostGIS, Alembic
migrations) and exposes FastAPI endpoints for draft CRUD, publish (draft → immutable
`ScenarioVersion`), clone, list/search and a validation endpoint wrapping
`validate_scenario_version`. Reuses the M1 domain models as the request/response shape rather
than forking a parallel schema. Did not implement the map/trajectory UI (M3) or SigMF ingest (M4).

### M4 — SigMF catalogue (in progress)

Branch `feature/sigmf-catalogue`. Ingests a SigMF `.sigmf-meta`/`.sigmf-data` asset pair already
uploaded to MinIO object storage: parses SigMF core metadata (`backend/rogue/catalogue/sigmf.py`,
pure/no I/O), streams the data object from S3 in bounded chunks to compute its checksum/length
(`backend/rogue/storage/object_store.py`), validates pairing/checksum/duration/metadata
(`backend/rogue/catalogue/ingest.py`, reusing `rogue.domain.validation.ValidationFinding`), and
persists the result as an immutable, versioned `IQRecording` row
(`backend/rogue/persistence/catalogue.py`) — mirroring M2's draft/validate/publish shape rather
than forking a parallel persistence pattern. Exposes `POST /recordings` (ingest; `recording_id`
omitted registers a new catalogue entry, given adds a new version to it),
`GET /recordings` (latest version per entry, filterable), `GET /recordings/{id}`,
`GET /recordings/{id}/versions[/{version}]`. Reuses M1's `IQRecording` domain model as-is (no new
fields added to it) and M2's `NotFoundError`/`ValidationRejectedError` so the existing exception
handlers apply unchanged. Unknown/unmapped SigMF metadata (remaining `global` keys, `captures`,
`annotations`, `collection`) is preserved verbatim in `extra_sigmf_fields` rather than dropped.
Does not implement recording deprecation/retirement (domain-model.md's "referenced records are
deprecated rather than destructively deleted" — no delete endpoint exists, so this is not yet a
concern) or a presigned-upload flow for getting bytes into MinIO in the first place; both are
left for a follow-up. RF/spectrum planning (M5) and Replay Plan compilation (M6) are out of scope.

## 4. Git workflow

- `main`: controlled release/integration baseline.
- `develop`: accepted development integration.
- `feature/<bounded-task>`: Claude/developer work.
- Pull Request into `develop` after tests and review.
- Never allow AI-generated broad refactors directly on `main`.

## 5. Claude-sized issues

Prefer issues such as:
- Define FrequencyEvent schema.
- Implement deterministic frequency behaviour.
- Add SigMF metadata parser.
- Compute spectrum occupancy at scenario time.
- Detect RF-window capacity conflicts.
- Implement Replay Plan schema.
- Implement simulated SDR Agent lease/watchdog.
- Add X440 capability discovery.

Avoid vague tasks such as “build the RF engine” or “build ROGUE”.

## 6. Definition of done

Each change must include, as applicable:
- architecture/schema impact documented;
- typed implementation;
- tests;
- format/lint/type checks;
- migration and compatibility notes;
- commands/results reported;
- no secrets or large I/Q assets committed;
- no unrelated refactoring.
