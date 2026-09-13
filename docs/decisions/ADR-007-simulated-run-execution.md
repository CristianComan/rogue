# ADR-007: Simulated Run Execution Scope (M7)

**Status:** Accepted baseline

## Context

M6 (`backend/rogue/compiler/`) produces an immutable `ReplayPlan` —
`allocations` (window → physical device/channel), `rf_windows`/
`realized_frequency_events`, and a `recording_manifest` pinned by content
hash — but nothing yet executes one. Per CLAUDE.md's priority order, M7 is
"Simulated SDR execution: full prepare/arm/start/stop without hardware,"
strictly before M8 ("Distributed SDR Agent: leases, cache, protocol,
watchdog, telemetry"). That ordering is the scope boundary this ADR
records: M7 proves the run **state machine** and domain contract
(`ScenarioRun`, leases, events) work correctly against a simulated adapter,
**in-process** inside the control plane — not over a network. M8 later
wraps this same orchestration to dispatch to real, separate Agent
processes over NATS; the existing `agents/common/main.py` is only an M0
presence-heartbeat placeholder and is untouched by M7.

This matches `docs/architecture/domain-model.md`'s diagram (`ScenarioRun` =
immutable `ReplayPlan` reference + `DeviceLease[]` + `RunEvent[]` +
evidence, "run evidence is append-only") and `sdr-architecture.md`'s
vendor-neutral `SDRAdapter` Protocol (section 2) and simulated-agent
requirement (section 8: "first-class, not throwaway").

## Decision

- **In-process only.** No NATS, no separate Agent process.
  `rogue.execution.adapter.MockSDRAdapter` runs inside the API process as a
  single, process-wide instance (`rogue.persistence.run._SIMULATED_ADAPTER`)
  — matching `docker-compose.yml`'s single `simulated-agent` service and
  "one Agent, many devices" (adapter methods are `(device_id,
  channel_index, ...)`-scoped, not one instance per channel).
- **Each physical channel is configured/armed/started once**, using its
  *earliest* allocation's window (`orchestrator._first_allocation_per_channel`).
  Runtime reconfiguration mid-run on a `BAND_SWITCH` event is not simulated
  in this pass; a scheduler loop that walks the compiled timeline live is
  deferred alongside the real distributed Agent work (M8).
- **Prefetch/verify is real, not simulated.** For each
  `RecordingManifestEntry`, `prepare_run` re-fetches the `IQRecording` from
  the catalogue and confirms its current `sha256_metadata`/`sha256_data`
  still match the plan's pinned values. This trusts the catalogue's stored
  hash columns rather than re-streaming and re-hashing the raw MinIO
  object — a stronger byte-level re-verification is a reasonable future
  hardening step, not done here.
- **Safety stance for this pass**: `ReplayPlan.safety_policy_outcome.
  tx_authorized` is `False` by the compiler's own design (a plan never
  authorizes transmission by itself). M7 has no real RF and no lease/
  watchdog policy engine yet (that's M8), so this pass does not add a
  local authorization step either — `prepare_run` only reserves/verifies/
  configures; it does not flip TX authorization on. Emergency-stop is
  still a first-class, always-available, dedicated-tested path regardless
  (CLAUDE.md section 10): `emergency_stop_run` is callable from *any*
  `RunStatus` — including `failed` — and always reaches
  `EMERGENCY_STOPPED`, sweeping every channel even if one channel's
  adapter call raises.
- **Append-only evidence enforced at the service layer**, not a DB
  constraint. `ScenarioRun` stays one JSONB document
  (`ScenarioRunORM.document`, mirroring `ScenarioDraftORM`'s mutable-
  document shape rather than `ReplayPlanORM`'s insert-only one) that only
  ever gets new events appended and its `status` advanced forward by
  `rogue.execution.orchestrator`. A separate insert-only `run_events`
  table would enforce this more strongly but is more schema than this pass
  needs — recorded as a follow-up, not silently dropped.
- **No lease expiry/renewal or watchdog.** `DeviceLease` is a shape
  placeholder — the real distributed lease lifecycle is M8's job.

## Consequences

- `rogue.execution.orchestrator`'s five lifecycle functions
  (`prepare_run`/`arm_run`/`start_run`/`stop_run`/`emergency_stop_run`) are
  pure and DB-free, mirroring `rogue.compiler.compile`'s split from
  `rogue.persistence.replay` — `rogue.persistence.run` does the
  surrounding read-current-document/call-orchestrator/write-back I/O, the
  same shape as `repository.update_draft` minus optimistic-concurrency
  revision checking (a run is orchestrator-driven, not concurrently
  hand-edited).
- `InvalidRunTransitionError` (wrong-status lifecycle call) maps to HTTP
  409, matching `ConflictError`'s precedent.
- M8 will need to replace `_SIMULATED_ADAPTER` with a real dispatch path to
  distributed Agent processes, add real lease expiry/watchdog, and decide
  where real TX authorization is granted — none of that is settled here;
  this ADR only fixes M7's boundary.
