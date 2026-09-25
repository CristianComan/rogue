# ROGUE SDR Architecture

## 1. SDR Agent pattern

Each SDR node runs a lightweight Agent adjacent to the hardware. The central control plane does not directly manipulate vendor drivers.

The Agent:
- discovers devices/channels and reports actual capabilities;
- maintains local SigMF cache;
- validates configuration against hardware and local policy;
- reserves exclusive resources using leases;
- configures and arms devices;
- executes scheduled replay using the best supported timing method;
- publishes acknowledgements, telemetry and alarms;
- enforces watchdog and fail-safe stop;
- records actual configuration readback and timing method;
- exposes vendor-neutral high-level operations.

SoapyRemote may be used for diagnostics, but is not the production orchestration abstraction.

**Implemented (M19a/M19b, ADR-019):** before this, the Agent process had
exactly one command ingress (NATS) and blocked on `nats.connect()` before it
would even start — so it could not run at all, let alone honor "watchdog and
fail-safe stop independent of control-plane availability" above, if NATS was
unreachable. `ROGUE_AGENT_INGRESS=local`/`both` starts a second, equally
first-class local HTTP command ingress (`agents/common/local_api.py`) and no
longer blocks startup on NATS reachability; `ROGUE_AGENT_LOCAL_RECORDING_ROOT`
(`agents/common/local_recording_source.py`) resolves PREFLIGHT's recordings
from a local SigMF root instead of MinIO. Together these let a
previously-validated replay run from a local command with no control plane
(NATS, MinIO, the database) reachable at all, terminating in the same
`AgentRuntime` handlers and the same adapter/watchdog — not a second Agent
implementation. See **Manual verification guide, §M19** for the exact
commands. The local API is plain HTTP, not HTTPS — it is bound to loopback
by default (`ROGUE_AGENT_LOCAL_API_HOST`), matching item 1's "loopback/
management-interface only" scope; binding it to a non-loopback management
interface without adding TLS in front of it is a deployment misconfiguration,
not something this ingress defends against on its own. `scripts/sdrctl`
(M19c, a CLI over this API) and the compiler `lo_groups`/bandwidth/gain-
ceiling additions (M19d) remain planned.

## 2. Vendor-neutral adapter contract

Conceptual interface:

```python
class SDRAdapter(Protocol):
    async def discover(self): ...
    async def capabilities(self): ...
    async def reserve(self, lease): ...
    async def preflight(self, recording, config): ...
    async def configure(self, config): ...
    async def arm(self, start_spec): ...
    async def start(self): ...
    async def stop(self): ...
    async def emergency_stop(self): ...
    async def status(self): ...
```

Implementations initially include:
- `MockSDRAdapter` / simulated agent;
- `EttusX440Adapter`;
- `DeepwaveAIR7311Adapter`.

Vendor libraries (UHD, SoapySDR, libiio or other device APIs) stay behind adapters.

**Implemented (M9/M10, ADR-009/ADR-010):** `agents/common/x440_adapter.py`'s
`EttusX440Adapter` (UHD) and `agents/common/air7311_adapter.py`'s
`DeepwaveAIR7311Adapter` (native SoapySDR), both thin subclasses of
`agents/common/sdr_adapter_base.StreamingSDRAdapter`, which holds the
vendor-agnostic lease/streaming logic behind a `RealDeviceSeam` so both are
unit-tested without either vendor SDK installed. **Neither is verified
against real hardware** — see ADR-009/ADR-010's explicit scope records.

## 3. Initial laboratory hardware profile

Initial target:
- 2 × Ettus USRP X440, modeled as 8 TX channels per unit (16 total working-profile channels);
- 2 × Deepwave AIR7311, modeled as 4 TX channels per unit (8 total working-profile channels);
- 24 physical TX channels in the initial planning pool.

Static profiles are planning defaults only. Runtime discovery/readback is authoritative.

The design baseline states that native X440 RF coverage does not cover 5.2/5.8 GHz. Therefore those bands are normally assigned to AIR7311-capable paths unless an explicit external frequency-conversion chain is modeled. X440 paths may serve 2.4 GHz and other supported sub-4-GHz windows.

**Implemented (M10, ADR-010):** `rogue.persistence.agents.
aggregate_capability_profile` builds a live `HardwareCapabilityProfile`
from every currently-online registered Agent of either family;
`rogue.persistence.replay.compile_and_store_replay_plan` schedules against
it by default, falling back to the static `DEFAULT_CAPABILITY_PROFILE`
only when no Agent is online — the compiler's existing capability-based
channel selection (`rogue/compiler/allocation.py`, unchanged) now actually
runs against real, connected hardware of both families instead of always
the illustrative default.

## 4. Agent command model

Versioned commands include:
- reserve / release / renew-lease;
- preflight (prefetch/verify);
- configure;
- arm;
- start / stop;
- emergency-stop;
- status.

Every command/ACK includes correlation ID, sequence, timestamps, state and structured errors. Commands are idempotent, expire, and are rejected when stale or outside an active lease.

**Implemented (M19a, ADR-019):** `agents/common/local_api.py` exposes
`POST /commands`, translating an `AgentCommand` request body directly into
the same `AgentRuntime.handle_command` call the NATS path's `_handle`
already uses — the command model above does not fork per ingress; a
request's `correlation_id` is the same field the NATS path's idempotency
handling already keys on, no new mapping needed. `main.py`'s NATS connect
becomes non-blocking (a bounded 5s best-effort attempt, then `nc=None`)
under `ROGUE_AGENT_INGRESS=local`/`both` so a control-plane outage cannot
prevent the Agent from starting or serving local commands; `AgentRuntime.run`
skips NATS subscribe/presence/telemetry when `nc` is `None` but still runs
the watchdog loop unconditionally.

**Implemented (M8, ADR-008):** `backend/rogue/protocol/messages.py` defines
`AgentCommand`/`AgentAck` (plus `AgentPresence`/`AgentTelemetry`) as the
concrete versioned shapes above; `subjects.py` gives each Agent its own
NATS request-reply command subject (`rogue.agents.{agent_id}.cmd`) and
telemetry subject (`rogue.agents.{agent_id}.telemetry`), alongside the
shared presence subject. `rogue.execution.remote_adapter.RemoteAgentAdapter`
is the control-plane side; `agents/common/agent.AgentRuntime` is the Agent
side. Lease expiry is real (`DeviceLease.expires_at`): the central
`rogue.execution.lease_sweep` task renews active runs' leases on a short
interval and emergency-stops one that lapses (rule 12's central half).

## 5. Timing and synchronization classes

| Level | Method | Intended use |
|---|---|---|
| L0 | simulated/no SDR | UI, scenario design, CI |
| L1 | NTP hosts + software barrier | early functional tests; ms to tens-of-ms |
| L2 | scheduled local future start | improved LAN repeatability |
| L3 | shared PPS/10 MHz or hardware PTP + timed commands | tightly aligned replay where supported |
| L4 | L3 + reference/loopback measurement | evidence-grade measured alignment |

A run declares required synchronization class/tolerance. The system must not promise hard real-time behaviour over ordinary Ethernet.

## 6. Local caching and streaming

I/Q is prefetched before a run, checksum-verified and replayed from local storage. Streaming uses bounded buffers; no full-file RAM load. The control network is not the sample transport path.

**Implemented (M19b, ADR-019):** before this, the only recording source
(`agents/common/cache.py`) fetched from MinIO — PREFLIGHT could not proceed
without it reachable either, even under local command ingress.
`agents/common/local_recording_source.py` adds a local-SigMF-root
alternative (`ROGUE_AGENT_LOCAL_RECORDING_ROOT`, symlinking a hash-verified
pair into the existing `cache_dir` rather than copying — a `.sigmf-data`
file can be many gigabytes), rejecting a missing metadata/data pair, a data
hash that doesn't match the pinned `sha256_data` (raised as the same
`cache.CacheVerificationError` the NATS path's exception handling already
knows about), and path traversal/symlink escape outside the configured
root. `agent.py`'s PREFLIGHT handling picks the source by whether
`AgentRuntime.local_recording_root` is set; everything downstream
(`_load_cached_recording`, the adapter itself) does not fork per source.

## 7. Safety

Agent safety is independent of control-plane availability:
- default deny TX;
- explicit RF approval/environment gate;
- local frequency/power/profile checks;
- cabled/attenuated mode by default for automated tests;
- lease expiry and watchdog stop;
- process termination stop where technically possible;
- emergency stop;
- reject unsigned/incorrect manifests and incompatible settings;
- record stop acknowledgements and faults.

Real hardware tests must never automatically enable uncontrolled over-the-air transmission.

**Implemented (M8, ADR-008):** enforced twice, matching CLAUDE.md rule 12.
Centrally, `rogue.execution.lease_sweep` renews every ARMED/RUNNING run's
leases and emergency-stops one whose lease lapses or fails to renew — this
still depends on the control plane itself being up. Locally,
`agents/common/agent.AgentRuntime` tracks last control-plane contact per
leased channel and emergency-stops its own adapter if a channel stays
armed/transmitting past a timeout with no contact, entirely independent of
whether the control plane is reachable — this is what actually covers a
dead/partitioned control-plane process, as opposed to a dead Agent process
(which the central sweep instead detects via a failed renewal request).

**Implemented (M9, ADR-009):** the "explicit RF approval/environment gate"
above is `settings.enable_real_tx`/`ROGUE_ENABLE_REAL_TX` (default
`False`), checked in `EttusX440Adapter.start()` — refuses to key the
transmitter and never touches the device otherwise. This is a local,
per-Agent-host interlock, separate from the compiler's
`SafetyPolicyOutcome.tx_authorized` (still a structural placeholder; a
full policy engine is a separate, later concern).

**Planned (M19c, ADR-019):** `scripts/emergency_stop.py` — local-only, no
auth, calls the local API's abort endpoint or, failing that, the adapter's
abort path directly. Independent of local command ingress landing at all.

## 8. Simulation first

The simulated agent is a first-class implementation, not a throwaway mock. It shall model transfer delay, clock drift, underrun, command loss, device failure and reconnect. This enables CI, operator training and orchestration development before hardware integration.
