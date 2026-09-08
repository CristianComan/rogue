# ADR-011: Temporary SoapyRemote Exception for M10 Agent Verification

**Status:** Accepted — explicitly temporary, dev/lab-only

## Context

M10's real hardware verification (`docs/testing/manual-verification-guide.md`
§"M10 — AIR7311 adapter") requires running `agents.common.main` /
`DeepwaveAIR7311Adapter` against a physical AIR7311. The lab unit currently
available (`airstack`, Deepwave image 2.4.1) ships Python 3.10.12 only, and
its `python3-soapysdr` package is a compiled extension ABI-locked to CPython
3.10. ROGUE requires Python 3.11+ at minimum (`datetime.UTC`), 3.12 as the
documented baseline (`deployment.md` §4). Building SoapySDR's Python bindings
from source against 3.12 directly on the Orin was considered but not
attempted this session in favor of a lower-risk path (see Decision).

ADR-005 §1 prohibits wiring vendor-library network remoting (`SoapyRemote`)
into any Agent, orchestration, or Replay Plan execution path, reserving it
for ad hoc bench diagnostics only. The rationale is protecting the
timing-precision guarantees ADR-004 exists for for the L3/L4 synchronization
classes (`sdr-architecture.md` §5), which matter starting at M11 (multi-SDR
synchronization).

**M10's own exit criterion does not involve synchronized multi-device timing
— it needs one AIR7311 to discover live capabilities and complete a
cabled/attenuated single- and two-channel replay.** M11 is Planned, not
started. This creates room for a narrowly-scoped exception rather than a
blanket reversal of ADR-005.

## Decision

For M10 verification only, on this specific lab unit, until it (or another
AIR7311 host) is reimaged with a Python 3.12-compatible on-device SoapySDR
build:

- Run `soapyremote-server`'s `SoapySDRServer` **on the Orin itself**
  (standard Ubuntu/jammy package, no source build, does not touch the
  existing 3.10 `python3-soapysdr` install or the vendor `soapysdr0.8-
  module-airt` driver module — both keep running locally on the Orin
  exactly as shipped).
- Run `agents.common.main` **on the control-plane host** (Ubuntu 24.04,
  system Python 3.12.3, `python3-soapysdr` 0.8.1 and `soapysdr0.8-module-
  remote` already apt-available and version-matched to the Orin's SoapySDR
  core), with `ROGUE_AIR7311_DEVICE_ARGS` pointing at
  `driver=remote,remote=192.168.68.59,remote:driver=SoapyAIRT` (or
  equivalent) instead of `driver=SoapyAIRT` directly.
- This is diagnostics-and-verification use, explicitly **not** a change to
  the documented production deployment model: ADR-004 (bare-metal, adjacent
  to hardware) and ADR-005 §1 (no remoting into the Agent path) remain the
  target architecture for real lab/production runs. A real Agent host still
  needs on-device Python 3.12 + matching SoapySDR bindings before this
  exception is retired.

## Rationale

- The alternative (rebuilding SoapySDR's Python bindings from source against
  3.12 on the Orin's aarch64/Jetson image) is a materially bigger, riskier
  change to lab hardware than adding one standard, already-packaged apt
  component (`soapyremote-server`) that doesn't touch the existing vendor
  install at all.
- M10's verification scope (live discovery, cabled TX/RX) has no timing
  precision requirement remoting would compromise; M11 (the milestone that
  actually needs ADR-004/005's guarantees) has not started.
- Keeping this documented and scoped (rather than an undocumented one-off)
  means it can't quietly become the assumed pattern once M11 sync work
  begins.

## Consequences

- `docs/testing/manual-verification-guide.md`'s M10 §Part B should note this
  exception and the exact device args used, once the run is actually
  exercised end to end.
- This ADR should be marked superseded/closed once any AIR7311 Agent host
  runs Python 3.12 natively with matching SoapySDR bindings — at that point
  ADR-005 §1 applies without exception again.
- Does **not** authorize `SoapyRemote` for `EttusX440Adapter`/UHD, for any
  M11+ synchronized run, or for any non-lab/production deployment.

## Outcome (2026-09-08)

This exception was exercised end to end and closed out M10's real-hardware
gap:

- `air7311-orin-01` registered online against `GET /agents` with live
  capabilities read back from the physical unit over the remote link.
- `rogue.persistence.replay.compile_and_store_replay_plan` correctly
  scheduled against it (`capability_profile.id == "live-agent-registry"`).
- A full replay run (`reserve -> prefetch_verified -> configure -> arm ->
  start`) executed successfully on channel 0 (`TX1`, the one leg of the
  loopback carrying a 40 dB physical attenuator to `RX1`) via
  `DeepwaveAIR7311Adapter.start()` with `ROGUE_ENABLE_REAL_TX=1` — SoapyRemote
  set up a real TX stream (`SoapyRemote::setupTxStream`) and streamed the
  recording to the physical hardware. The run was then stopped cleanly
  (`stopped` event, `RunStatus.STOPPED`).
- Channel 1 (`TX2`) was **not** exercised with real TX in this session — its
  loopback to `RX2` had no attenuator connected, so real TX was deliberately
  withheld there per CLAUDE.md rule 10/12.
- This session also found and fixed two real bugs in the distributed dispatch
  path that had never been exercised against a real (non-mock) adapter
  before now — see `agents/common/agent.py`'s `_load_cached_recording` (the
  PREFLIGHT handler previously passed a hardcoded empty recordings list to
  `adapter.preflight()`, which `MockSDRAdapter` silently tolerates but any
  real `StreamingSDRAdapter` subclass rejects) and the still-open gap in
  `backend/rogue/execution/remote_adapter.py`'s `_send` (discards the real
  `ack.error` detail on a rejected command, raising a generic
  `SimulatedDeviceFailureError` instead — cost real debugging time here and
  is worth a follow-up fix, independent of this ADR's scope).
- Also surfaced: `agents/common/sdr_adapter_base.py`'s `configure()` uses a
  hardcoded `DEFAULT_GAIN_DB = 0.0` (max gain) with no scenario-level way to
  request lower gain — fine behind real attenuation (as used here) but a
  real gap for any future direct-connect bench setup, and eventually for
  real antenna deployments needing a non-zero gain plan. Not fixed here;
  flagged as a follow-up.
