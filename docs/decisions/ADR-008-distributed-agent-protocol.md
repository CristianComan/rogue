# ADR-008: Distributed Agent Protocol Scope (M8)

**Status:** Accepted baseline

## Context

M7 (`feature/simulate-sdr-execution`, ADR-007) proved the `ScenarioRun`
prepare/arm/start/stop/emergency-stop state machine against a single
in-process `MockSDRAdapter` — no NATS, no separate Agent process. Per
CLAUDE.md's priority order, M8 is "Distributed SDR Agent: leases, cache,
protocol, watchdog, telemetry," and ADR-007's Consequences section already
names the work this hands off: replace `_SIMULATED_ADAPTER` with a real
dispatch path to distributed Agent processes, add real lease expiry/
watchdog, and decide where real TX authorization is granted (deferred
again here — `ReplayPlan.safety_policy_outcome.tx_authorized` stays a
structural `False` placeholder; this ADR does not touch it).

This ADR fixes what "distributed" means for M8: a real Agent process,
reached over NATS, still backed by the same simulated `MockSDRAdapter` —
real vendor hardware stays M9/M10 per CLAUDE.md's explicit sequencing.

## Decision

- **Protocol module lives at `backend/rogue/protocol/`**, not a new
  top-level `schemas/` package. The `rogue` package is already installed
  in full into the Agent image (`agents/Dockerfile`'s `pip install .`), so
  this needs no new packaging boundary. `schemas/` (CLAUDE.md §6) stays an
  intentionally unused placeholder for now; revisit if a bare-metal Agent
  host ever needs a dependency-light install that excludes the rest of
  `rogue` (M9/M10 concern, not this one).
- **Command/reply is NATS request-reply**, one subject per agent
  (`rogue.agents.{agent_id}.cmd`), not a shared subject with agent_id in
  the payload — this lets NATS itself do the routing/queueing per agent.
  Every `AgentCommand`/`AgentAck` carries `schema_version`,
  `correlation_id`, `sequence` and a timestamp (`sdr-architecture.md` §4).
  Telemetry is a separate fire-and-forget publish subject
  (`rogue.agents.{agent_id}.telemetry`); presence keeps the existing
  `rogue.agents.presence` subject from the M0 placeholder, now with real
  reported capabilities instead of just a mode string.
- **Two simulated Agent processes in docker-compose**
  (`simulated-agent-1`/`simulated-agent-2`), each owning a disjoint slice
  of `DEFAULT_CAPABILITY_PROFILE`'s device_ids (`ROGUE_AGENT_DEVICE_IDS`).
  This is a deliberate choice over keeping one Agent: with only one, the
  control plane's device_id→agent_id registry lookup has exactly one
  possible answer and the routing code it exists to prove is never
  actually exercised end-to-end, only unit-tested against a fake.
- **Lease TTL + renewal, enforced twice.** `DeviceLease` gains
  `expires_at`. The control plane's lease-sweep task (`rogue.execution.
  lease_sweep`) renews leases on every active (ARMED/RUNNING) run on a
  short interval and emergency-stops any run whose lease has expired
  without renewal — this is the *central* half of CLAUDE.md rule 12. Each
  Agent process independently tracks last-contact time per leased channel
  and emergency-stops its own adapter if a channel stays armed/
  transmitting past a timeout with no control-plane contact — the *local*
  half, working even if the control plane itself is unreachable
  (`sdr-architecture.md` §7).
- **Dispatch mode is a settings switch, not a code fork.**
  `rogue.persistence.run` keeps constructing an in-process `MockSDRAdapter`
  by default (`ROGUE_AGENT_DISPATCH_MODE=in_process`), which is what the
  existing unit test suite exercises unchanged. docker-compose's `api`
  service sets `ROGUE_AGENT_DISPATCH_MODE=distributed`, which wires a new
  `RemoteAgentAdapter` (same `SDRAdapter` Protocol) that dispatches over
  NATS instead. This is a deployment-topology setting, analogous to tests
  using a different `ROGUE_DATABASE_URL` than compose — not a
  backwards-compatibility shim (CLAUDE.md §9).
- **`SimulatedDeviceFailureError` becomes one case of a new
  `AdapterOperationError` base** (`rogue.execution.adapter`), so
  `rogue.execution.orchestrator`'s existing per-step exception handling
  needs no new branches when talking to a remote Agent —
  `RemoteAgentAdapter` raises a new `AgentUnreachableError(
  AdapterOperationError)` on a command timeout/no-responders, which the
  orchestrator's existing `except AdapterOperationError` clauses already
  fail the run on, the same way a simulated device failure does today.
- **Real local SigMF cache on the Agent side.** Each Agent downloads and
  hash-verifies `.sigmf-meta`/`.sigmf-data` from MinIO into a local
  directory during `PREFLIGHT`, reusing `rogue.storage.object_store`'s
  existing bounded-streaming reads as-is — this is new versus M7, where
  `prepare_run` only re-checked the catalogue's stored hash columns
  without an Agent process to actually cache bytes into.

## Consequences / explicit exclusions

- Real vendor adapters (`EttusX440Adapter`, `DeepwaveAIR7311Adapter`) are
  unchanged — still M9/M10.
- Timing sync beyond L1 (NTP + software barrier, already implicit in
  `start_at_seconds`) is not implemented; L2-L4 barrier/PTP work stays
  M11.
- Telemetry is live-only. The control plane does not persist a queryable
  telemetry time-series in this pass — a reasonable follow-up, not
  silently dropped.
- NATS has no auth/TLS in dev or compose. Per-agent machine credentials
  remain the open item `deployment.md` §6 already recorded.
- The lease-sweep renewal loop appends one `RunEvent` per tick to an
  active run's evidence log; for a long-running run this grows
  unboundedly with wall-clock time rather than with actual state
  transitions. Acceptable for this milestone's short simulated runs;
  flagged as a follow-up if runs are expected to stay ARMED/RUNNING for
  extended periods.
- `RemoteAgentAdapter.discover()`/`status()` are not wired into any new
  per-request endpoint beyond the presence-driven `GET /agents` registry
  (which reflects the last heartbeat, not a live round trip) — a live
  discovery-refresh endpoint is a reasonable future addition.
