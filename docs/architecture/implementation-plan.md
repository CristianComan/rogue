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
| — | Recording schedule + spectrum waterfall | per-platform recording/background/silence scheduling, real spectrogram preview | Done — `feature/recording-schedule-waterfall`, merged to `develop` (supplemental; not in the original CLAUDE.md M-sequence, added by direct request) |
| M6 | Replay Plan compiler | scenario compiles to hardware-neutral executable plan | Done — `feature/replay-plan-compile`, merged to `develop` |
| M7 | Simulated SDR execution | full prepare/arm/start/stop without hardware | Done — `feature/simulate-sdr-execution` |
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
  it does not bind a scenario to a specific SDR/device (CLAUDE.md rule 1, ADR-002). The properties
  column also gained `MissionsListEditor`/`ReceiversListEditor`/`TimelineEventsListEditor` (mirroring
  the existing `ZonesListEditor`) — previously a mission/receiver could only be selected by clicking
  its map feature, and a timeline event (no geometry at all) had no way to be re-selected once
  deselected.
- **`ScenarioDraft`/`ScenarioVersion.recordings` is now always server-derived**, never
  hand-authored. It used to be a flat list edited through a standalone `RecordingsListEditor` panel,
  disconnected from where recordings are actually scheduled — `Mission -> RfLink -> RfEmission`
  already carries that (with `start_offset`/`duration_override`/`loop`). Checking its only consumer
  found it was `validate_scenario_version`'s `dangling_recording_reference` check, which verified
  self-consistency against that same hand-authored list and nothing about the real catalogue — so it
  came out too, as structurally unreachable once the list can no longer diverge from the emissions
  that populate it. `derive_recording_references` (`backend/rogue/domain/scenario.py`) now builds it
  by walking `missions[].rf_links[].emissions[]` at draft create/update time; `DraftContent`
  (`api/schemas.py`) no longer accepts `recordings` as client input (422 if sent);
  `RecordingsListEditor.tsx` is deleted. The field stays on the schema for backward
  read-compatibility (`extra="forbid"` on `RogueModel` would otherwise break reading every existing
  stored draft/version) and as a useful denormalized manifest. While fixing the e2e coverage for
  this, also fixed a real pre-existing bug in `RecordingPicker.tsx`: selecting "Custom UUID…" reset
  the value to `""`, which doesn't count as "custom" by the component's own check, so the text input
  never appeared.
- **ADR-005** (`docs/decisions/ADR-005-sdr-adapter-library-choice.md`) records a related but
  separate decision reached while scoping this work: SDR adapters stay split by vendor library
  (native UHD for X440, native SoapySDR for AIR7311) rather than unified via SoapyUHD, and
  `SoapyRemote` stays diagnostics-only, never the production access path. No adapter code was
  written — that's still M9/M10, per CLAUDE.md's explicit sequencing rule.

Backend (172 tests) and frontend (118 tests) both green as of this increment, plus a 3-test
Playwright e2e suite covering create→validate→save→publish, overlapping-emissions publish
rejection, and 409 stale-revision conflicts. A real "does this recording exist in the catalogue"
validation still doesn't exist (the retired check never actually verified that either) — flagged as
a natural follow-up, not bundled into this pass.

### M6 — Replay Plan compiler (done)

Branch `feature/replay-plan-compile`, based on `develop` after the
recording-schedule/waterfall supplemental. New `backend/rogue/compiler/`
package (mirroring `backend/rogue/spectrum/`'s pure-function-then-
persistence-wrapper shape): `frequency.py` realizes SCRIPTED/
PROBABILISTIC_ADAPTIVE frequency-agility over a full compile horizon
(reusing a small extraction from M5's `spectrum/occupancy.py` —
`probabilistic_dwell_segments` — so the seeded-RNG dwell math has one
implementation, not two); `windows.py` packs co-occurring occupied bands
(via M5's `compute_spectrum_state`, evaluated at every occupancy-changing
instant) into `RfWindow`/`CompositeChannel` spans; `allocation.py` assigns
each window span to a physical TX channel from a `HardwareCapabilityProfile`
(stable-preferring, first-fit); `compile.py` orchestrates all three into an
immutable `ReplayPlan`. See ADR-006 for the exact packing/allocation
algorithm and its limits, and `models.py`'s `DEFAULT_CAPABILITY_PROFILE`
for the illustrative 24-channel default (CLAUDE.md section 4).

"Hardware-neutral" per this milestone's exit criterion means the compiler
takes `HardwareCapabilityProfile` as a compile-time input (defaulting to
the illustrative profile above) rather than runtime-discovered hardware —
real capability readback is M8/M10, per CLAUDE.md rule 10 and the
explicit M1-M14 sequencing. `Receiver` geometry, Doppler/delay/phase and
aggregate peak/RMS/intermodulation assessment are correspondingly out of
scope (M12-M14); `SafetyPolicyOutcome.tx_authorized` is a structural
`False` placeholder (rule 12) — the full lease/policy engine is M8.

Persisted the same way as M2/M4's immutable artifacts: a new `replay_plans`
JSONB-document table (migration `8c4f3a1e6b2d`, since a new table needs one,
unlike M4/M5's additive-JSONB-field changes), `rogue.persistence.replay`
mirroring `rogue.persistence.spectrum`'s "resolve inputs, call the pure
function" shape but persisting on success (`repository.
CompilationRejectedError` mirrors `ValidationRejectedError` when the plan
has BLOCKING findings — nothing is persisted in that case). API:
`POST /scenarios/{id}/versions/{n}/compile` (idempotency-key-wrapped, 201),
`GET .../replay-plans`, `GET .../replay-plans/{id}` — compiles a
*published* `ScenarioVersion`, not a draft, keeping the compiler's input
immutable (rule 11).

Backend test suite grew from 172 to 207 tests: pure-function tests under
`tests/unit/compiler/` (frequency realization, window packing, channel
allocation, end-to-end compile determinism), a DB-backed
`tests/unit/persistence/test_replay.py`, and an HTTP-level
`tests/unit/api/test_replay_compiler.py` (named to avoid a pytest module-
name collision with the persistence test file, matching M5's
`test_spectrum.py`/`test_spectrum_planner.py` precedent). A real "does the
scenario have an explicit total duration" concept still doesn't exist
(mission timing is M3's unfinished job) — the compile endpoint takes an
explicit `duration_s` horizon instead, the same shape as M5's `at_seconds`
single-instant query, generalized to a span.

### M7 — Simulated SDR execution (done)

Branch `feature/simulate-sdr-execution`, based on `develop` after M6. New
domain model `backend/rogue/domain/run.py` (`ScenarioRun`, `RunStatus`,
`DeviceLease`, `RunEvent`/`RunEventKind`) and a new `backend/rogue/
execution/` package: `adapter.py` defines the vendor-neutral `SDRAdapter`
Protocol (sdr-architecture.md section 2) plus `MockSDRAdapter`, a
first-class simulated implementation with per-channel state, a small
simulated transfer delay, and an injectable `fail_on` hook so tests can
force a specific `(device_id, channel_index, method)` call to raise
`SimulatedDeviceFailureError`; `orchestrator.py` is the pure, DB-free
prepare/arm/start/stop/emergency-stop state machine (mirrors `compiler/
compile.py` vs `persistence/replay.py`'s split). See ADR-007 for the exact
scope decisions and their rationale — in-process only (no NATS, no
separate Agent process; that's M8), one earliest-allocation configuration
per physical channel, real prefetch/hash-verification against the
catalogue, and emergency-stop as an always-reachable, always-succeeding
path from any `RunStatus` including `failed`.

Persisted like M2's `ScenarioDraftORM` (mutable JSONB document, not M6's
insert-only pattern): a new `scenario_runs` table (migration
`1e17dd5b4902`), `rogue.persistence.run` doing read-current-document →
call the matching pure `orchestrator` function → write the updated
document back, against a single process-wide `MockSDRAdapter` instance.
API: `POST /scenarios/{id}/replay-plans/{plan_id}/runs` (create+prepare,
idempotency-key-wrapped, 201), `POST .../runs/{run_id}/{arm,start,stop}`
(also idempotency-key-wrapped, 200), `POST .../runs/{run_id}/emergency-stop`
(no idempotency key — always accepted, never blocked), `GET .../runs/
{run_id}`, `GET .../runs`. `InvalidRunTransitionError` (wrong-status
lifecycle call) maps to HTTP 409.

Backend test suite grew from 207 to 254 tests: `tests/unit/domain/
test_run.py`, `tests/unit/execution/{test_adapter,test_orchestrator}.py`
(pure, including dedicated emergency-stop-from-armed/running/failed tests
per CLAUDE.md section 10), `tests/unit/persistence/test_run_execution.py`
(named to avoid a pytest module-name collision with the domain test file,
matching M6's `test_replay_compiler.py` precedent), and `tests/unit/api/
test_runs.py`. Manually verified end-to-end against a live server: compile
a plan, walk create→arm→start→stop via curl with `GET .../runs/{id}`
confirming a strictly growing event list at each step, and a separate
emergency-stop mid-`running` reaching `emergency_stopped`.

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
