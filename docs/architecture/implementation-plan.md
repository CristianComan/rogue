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
| M4 | SigMF catalogue | validated immutable recording assets | Done — `feature/sigmf-catalogue`, merged to `develop` |
| M5 | RF spectrum planner | deterministic spectrum state and conflict/headroom findings | Done — `feature/rf-spectrum-planner`, merged to `develop` |
| — | Recording schedule + spectrum waterfall | per-platform recording/background/silence scheduling, real spectrogram preview | In progress — `feature/recording-schedule-waterfall` (supplemental; not in the original CLAUDE.md M-sequence, added by direct request) |
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

### M4 — SigMF catalogue (done)

Branch `feature/sigmf-catalogue`, merged to `develop` via GitHub PR #3. Ingests a SigMF
`.sigmf-meta`/`.sigmf-data` asset pair already uploaded to MinIO object storage: parses SigMF core
metadata (`backend/rogue/catalogue/sigmf.py`, pure/no I/O), streams the data object from S3 in
bounded chunks to compute its checksum/length (`backend/rogue/storage/object_store.py`), validates
pairing/checksum/duration/metadata (`backend/rogue/catalogue/ingest.py`, reusing
`rogue.domain.validation.ValidationFinding`), and persists the result as an immutable, versioned
`IQRecording` row (`backend/rogue/persistence/catalogue.py`, JSONB-backed — no migration needed for
later additive field changes) — mirroring M2's draft/validate/publish shape rather than forking a
parallel persistence pattern. Exposes `POST /recordings` (ingest; `recording_id` omitted registers
a new catalogue entry, given adds a new version to it), `GET /recordings` (latest version per
entry, filterable), `GET /recordings/{id}`, `GET /recordings/{id}/versions[/{version}]`. Reuses
M1's `IQRecording` domain model as-is (no new fields added to it in this milestone) and M2's
`NotFoundError`/`ValidationRejectedError` so the existing exception handlers apply unchanged.
Unknown/unmapped SigMF metadata (remaining `global` keys, `captures`, `annotations`, `collection`)
is preserved verbatim in `extra_sigmf_fields` rather than dropped. Does not implement recording
deprecation/retirement or a presigned-upload flow for getting bytes into MinIO in the first place;
both are left as follow-ups. RF/spectrum planning (M5) and Replay Plan compilation (M6) were out
of scope for this milestone.

### M5 — RF spectrum planner (done)

Branch `feature/rf-spectrum-planner`, merged to `develop`. Deterministic occupancy + conflict/
headroom findings computed at an arbitrary scenario time from authored `DroneRfLink`/`RfEmission`
data plus the M4 catalogue, in `backend/rogue/spectrum/occupancy.py` (pure) and exposed via
`backend/rogue/api/spectrum.py`/`backend/rogue/persistence/spectrum.py`. Per CLAUDE.md rule 5,
spectral overlap between different links is legal by default (advisory WARNING), while an occupied
band that doesn't fit inside its own link's declared `RfBand` is BLOCKING. Also added recording-
picker UI groundwork on the frontend (`RecordingPicker.tsx`, `api/recordings.ts`) reused by the
next increment below. RF Environment Compiler / Replay Plan generation (M6) remains out of scope.

### Recording schedule + spectrum waterfall (in progress, supplemental)

Branch `feature/recording-schedule-waterfall`, based on `develop` after M5. Not part of the
original CLAUDE.md M1–M14 sequence — added by direct request, sitting architecturally between M4
and M5's dependencies (scenario domain model + catalogue) rather than blocking on M6+. Scope:

- **Domain**: `IQRecording.kind` (`signal`/`background`, set at ingest — `backend/rogue/domain/recording.py`);
  `RfEmission.recording` is now optional (`null` authors an explicit silence span, requiring
  `duration_override` since there's no recording to derive a length from —
  `backend/rogue/domain/rf.py`); a new `overlapping_emissions` BLOCKING validation finding for
  emissions with resolvable (explicit-duration) spans that overlap in time
  (`backend/rogue/domain/validation.py`).
- **Spectrogram preview**: computed once at ingest as a coarse overview (fixed, small time-bin
  count spanning the full `duration_s`), stored as an extra key in `IQRecordingORM.document`
  (JSONB — no migration needed), rather than recomputed live per request. A first live-STFT-per-
  request version was built and measured against realistic sample rates before this decision: a
  20 Msps recording's 2-second scrub window alone decodes to ~640 MB, which is too expensive to
  compute synchronously per request, especially with multiple Waterfall panels open during
  playback — so the endpoint now slices/looks up the precomputed overview instead.
  `storage/object_store.py:get_object_range` (bounded MinIO range-read) and
  `catalogue/spectrogram.py:compute_spectrogram` (the STFT itself) are reused for the ingest-time
  computation; only *when* they run changed. Frontend `components/timeline/Waterfall.tsx` renders
  the result as a canvas heatmap, re-centered on the link's live authored frequency.
- **Authoring UI**: `RfLinkForm.tsx` gained a "Silence" toggle per emission and a non-binding
  "Resource preference" section (`ResourcePreference.preferred_agent_tags`/`required_sync_class`/
  `notes` — already modelled in M1, never previously exposed in the UI). This is a preference only;
  it does not bind a scenario to a specific SDR/device (CLAUDE.md rule 1, ADR-002).
- **ADR-005** (`docs/decisions/ADR-005-sdr-adapter-library-choice.md`) records a related but
  separate decision reached while scoping this work: SDR adapters stay split by vendor library
  (native UHD for X440, native SoapySDR for AIR7311) rather than unified via SoapyUHD, and
  `SoapyRemote` stays diagnostics-only, never the production access path. No adapter code was
  written — that's still M9/M10, per CLAUDE.md's explicit sequencing rule.

Backend (164 tests) and frontend (115 tests) both green as of this increment; e2e coverage for the
new silence/overlap/waterfall paths and full manual browser verification are still outstanding.

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
