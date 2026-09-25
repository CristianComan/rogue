# ADR-019: Agent Local Command Mode (M19)

**Status:** Accepted. M19a (local HTTP ingress) and M19b (local recording
source) are implemented; M19c (`sdrctl`/`emergency_stop.py`), M19d (compiler
`lo_groups`/bandwidth/gain-ceiling additions) and M19e (conducted loop-test
suite) remain outstanding, tracked independently per the Consequences
section below.

## Context

A "Standalone SDR Replay Control" design document proposed building a second,
fully independent application — its own Agent process, its own Controller,
its own scenario/node/waveform YAML schema, its own REST API, its own replay
state machine and `ReplayBackend` abstraction, its own shared-LO/bandwidth/
gain validation — to let a technician run a previously-validated AIR7311
replay from local YAML + CLI when the ROGUE control plane is unavailable,
with ROGUE integrating with it later through a bridging adapter.

Reviewing that document against `develop` (M0–M18) found the premise wrong:
ROGUE already has a real, hardware-verified SDR execution layer
(`agents/common/sdr_adapter_base.StreamingSDRAdapter`, subclassed by
`EttusX440Adapter` and `DeepwaveAIR7311Adapter`; ADR-009/ADR-010), already
run to completion against a physical AIR7311 over real TX (ADR-011's
outcome). Building a second Agent/adapter/schema for the same hardware would
mean two independent safety gates and two gain-default implementations that
can silently diverge on what is safe to transmit — the exact duplication
CLAUDE.md rule 3 (vendor drivers stay behind one adapter layer) exists to
prevent.

The underlying operational need is real, though: confirmed by reading
`agents/common/main.py` and `agent.py`, the Agent process today has exactly
one command ingress and one recording source, and both hard-depend on the
control plane being reachable:

- `main.py::run()` calls `await nats.connect(nats_url)` before constructing
  `AgentRuntime` at all — if NATS is unreachable, the process never starts.
- Every command (`reserve`/`prefetch`/`configure`/`arm`/`start-at`/`stop`/
  `emergency-stop`/`status`) arrives exclusively on the per-agent NATS
  subject `rogue.agents.{agent_id}.cmd` (ADR-008). There is no HTTP or other
  local ingress.
- `agents/common/cache.py` fetches `.sigmf-meta`/`.sigmf-data` from MinIO
  (`rogue.storage.object_store`) — there is no path to a locally-resident
  SigMF file, so PREFLIGHT cannot proceed without MinIO reachability either.

So "run a validated replay with the control plane down" is a genuine,
currently unmet gap, not something ADR-008 already covers. ADR-008 itself
frames the Agent-side watchdog as running "independent of control-plane
reachability" (`sdr-architecture.md` §7) — that intent stops at the
watchdog; command ingress and recording sourcing were never made to match
it.

Separately, comparing the design document's validation rules (shared-LO
channel pairing, TX-bandwidth transition margin, gain/attenuation safety
ceiling) against `backend/rogue/compiler/allocation.py` and `models.py`
found all three genuinely absent from ROGUE today:

- `PhysicalTxChannelCapability` (models.py) has no LO-grouping field.
  `coherent_group_id` (ADR-012/013) is an unrelated concept — it forces
  independent windows for the same signal replicated to different receivers
  onto *distinct* channels for TDOA/AOA fan-out. It says nothing about two
  channels that must share one physical LO and therefore constrain each
  other's simultaneous tuning.
- `_channel_fits()` (allocation.py) checks only a single channel's own
  `max_usable_bandwidth_hz` and `tunable_ranges_hz` against the window. There
  is no `occupied_bandwidth_hz`/`transition_margin_hz` split anywhere in the
  window/capability models.
- `gain_db`/`tx_gain`/`attenuation` have zero occurrences in
  `backend/rogue/compiler` or `backend/rogue/domain`. The only gain value in
  the entire system is `agents/common/sdr_adapter_base.DEFAULT_GAIN_DB =
  0.0`, hardcoded, already flagged as a gap by ADR-011's outcome note ("no
  scenario-level way to request lower gain").

## Decision

Do not build a second application. Extend the existing Agent with a second,
equally first-class command ingress and recording source, and close the
three compiler gaps above. Both ingress paths terminate in the same
`AgentRuntime` handlers, the same `SDRAdapter.reserve/preflight/configure/
arm/start/stop`, the same watchdog — nothing about the hardware or safety
layer forks.

1. **`agents/common/local_api.py`** — a FastAPI app bound to loopback/
   management-interface only, translating HTTP requests directly into the
   existing `AgentCommand`/`AgentAck` calls the NATS path already uses.
   `command_id` maps onto ADR-008's existing `correlation_id` idempotency
   handling — this is a protocol adapter, not new command semantics.
2. **`agents/common/local_recording_source.py`** — resolves a logical
   `waveform_id` to a `.sigmf-meta`/`.sigmf-data` pair under a configured
   local root, verifies hashes, and produces the same `IQRecording` object
   `cache.ensure_cached` produces today, so `agent.py`'s
   `_load_cached_recording` does not fork per ingress path. Rejects path
   traversal, symlink escape outside the configured root, missing
   metadata/data pairs, and unsupported datatypes — the same reject list
   `cache.py` already enforces for the MinIO path.
3. **`agents/common/local_scenario.py`** — parses a local-mode scenario
   document built from the existing `rogue.compiler.models`/
   `rogue.domain.recording` types. No new scenario schema; a flatter
   authoring format for a technician, if wanted, is a YAML front-end that
   constructs the same typed models the compiler already validates.
4. **`main.py` gains `ROGUE_AGENT_INGRESS=nats|local|both`.** In `local`/
   `both`, `nats.connect()` is attempted but does not block startup;
   presence/telemetry publish opportunistically when reachable. This also
   fixes a latent gap relative to ADR-008's own stated intent: today the
   Agent process cannot even start, let alone run its local watchdog,
   without NATS reachable at boot.
5. **`scripts/sdrctl`** — a Typer CLI against the local API
   (`validate`/`prepare`/`arm`/`start`/`status`/`stop`), for use with no
   ROGUE UI, database, or broker running.
6. **`scripts/emergency_stop.py`** — local-only, no auth, calls the local
   API's abort endpoint or, if that is itself down, calls the adapter's
   abort path directly. Independent of the rest of this ADR.
7. **Compiler additions** (`rogue/compiler/`): an `lo_groups` declaration on
   `HardwareCapabilityProfile`/`PhysicalTxChannelCapability`, with an
   atomic-pair allocation check analogous to `_allocate_coherent_unit`'s
   pattern but enforcing *compatible simultaneous tuning within one LO's
   passband* rather than *distinct channels*; an `occupied_bandwidth_hz`/
   `transition_margin_hz` split enforced in `_channel_fits`; and a
   gain-safety ceiling threaded from scenario/site policy through a
   `CompilerFinding` to the adapter, replacing the hardcoded
   `DEFAULT_GAIN_DB`. These apply to both ingress paths — they are compiler/
   allocation fixes, not local-mode-specific.
8. **Conducted loop-test suite** (`tests/hardware/`): adopt the source
   document's three cabled topologies (one-TX-to-one-RX baseline matrix,
   one-TX/1:4-splitter/four-RX, four-TX/4:1-combiner/one-RX with
   coherent-worst-case combiner-power validation) as a new, explicit
   hardware-verification milestone against the real AIR7311 pair already
   proven in ADR-010/ADR-011. This closes a real gap in
   `verification-validation.md`, independent of everything else in this
   ADR.

## Non-goals

- No second `SDRAdapter`/`ReplayBackend` implementation. `MockSDRAdapter`/
  `EttusX440Adapter`/`DeepwaveAIR7311Adapter` are already that ladder.
- No second Agent state machine, no second repository, no
  `nodes.yaml`/`waveforms.yaml`/scenario-YAML trio, no later "bridging
  adapter" — there is nothing to bridge, this was never a separate system.
- No change to NATS as the primary/control-plane-driven ingress; local mode
  is additive.
- No streaming of IQ over the local API — the local API carries commands and
  status only, same boundary as the NATS path (`sdr-architecture.md` §4/§6).
- Full hardware-timed start / external trigger / PPS-disciplined start
  remain out of scope — ADR-013 already established that neither real
  adapter exposes any PPS/PTP/timed-command capability today, so this ADR
  does not attempt to promise better than the existing L1 (software-barrier)
  synchronization class.

## Consequences

- `agents/common/main.py`'s NATS-connect-blocking behavior changes for
  `local`/`both` ingress modes; `nats` ingress mode (today's only mode)
  is unaffected — existing docker-compose deployment behavior does not
  change unless `ROGUE_AGENT_INGRESS` is explicitly set.
- `HardwareCapabilityProfile` gains an `lo_groups` field; existing profiles
  (including `DEFAULT_CAPABILITY_PROFILE`) must supply it (empty/absent
  meaning "no shared-LO constraint declared") so existing compiler tests
  against profiles with no LO grouping are unaffected.
- `DEFAULT_GAIN_DB` stops being the only gain value in the system; call
  sites in `sdr_adapter_base.py` that assumed it need a follow-up pass once
  the policy field lands (tracked as part of item 7, not deferred silently).
- Local-mode PREFLIGHT bypasses the catalogue database entirely (same as
  the NATS path already does per ADR-008 — the Agent has no catalogue
  access either way), but also bypasses MinIO; recordings must already be
  present under the configured local root before a run.
- Milestones M19a–M19e (ingress + idempotent translation; local recording
  source + scenario reuse; `sdrctl` + `emergency_stop.py` + acceptance test;
  compiler shared-LO/bandwidth/gain rules; conducted loop-test suite) are
  independently shippable feature branches off `develop`, each with its own
  tests per CLAUDE.md §11 — this ADR does not require them to land together.

## Technical references

- Deepwave AIR-T FAQ and SoapyAIRT guidance: https://docs.deepwave.ai/faq/
- Deepwave AirStack clocking and timing:
  https://docs.deepwave.ai/AirStack/Core/programming_guide/clocking/
- Deepwave AIR7311 product documentation:
  https://docs.deepwave.ai/AIR-T/Products/AIR7311/
- SigMF specification: https://sigmf.org/
