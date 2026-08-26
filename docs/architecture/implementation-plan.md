# ROGUE Implementation Plan

## 1. Development strategy

Build ROGUE in bounded, testable increments. Do not begin with hardware-specific replay. Establish scenario semantics, schemas, Replay Plan and simulation first.

## 2. Recommended sequence

| Milestone | Deliverable | Exit criterion | Status |
|---|---|---|---|
| M0 | Repository, architecture docs, CI, Compose, UI/API shell, simulated agent | one-command local environment and health tests | Done |
| M1 | Scenario domain model | typed/versioned scenario round-trip with tests | Done — `backend/rogue/domain/`, merged to `develop` |
| M2 | Scenario persistence/API | draft/version/clone/validation APIs | In progress — `feature/scenario-persistence-api` |
| M3 | Map + trajectory editor | multi-drone scenario visual playback | Planned |
| M4 | SigMF catalogue | validated immutable recording assets | Planned |
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

### M2 — Scenario persistence/API (in progress)

Branch `feature/scenario-persistence-api`. Persist `Scenario`/`ScenarioDraft`/`ScenarioVersion`
(SQLAlchemy 2 + PostgreSQL/PostGIS, Alembic migrations) and expose FastAPI endpoints for draft
CRUD, publish (draft → immutable `ScenarioVersion`), clone, list/search and a validation endpoint
wrapping `validate_scenario_version`. Reuse the M1 domain models as the request/response shape;
do not fork a parallel schema. Do not implement the map/trajectory UI (M3) or SigMF ingest (M4)
in this feature.

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
