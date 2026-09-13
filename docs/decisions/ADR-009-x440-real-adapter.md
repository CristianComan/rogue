# ADR-009: First Real Adapter Scope (M9, Ettus X440)

**Status:** Accepted baseline — **hardware-unverified**

## Context

Per `docs/architecture/implementation-plan.md`, M9 is "First real adapter:
cabled/attenuated replay on one supported device." Per ADR-005, the first
real adapter targets the Ettus X440 via native UHD Python bindings.

**This session's development environment has no UHD/SoapySDR Python
packages and no physical X440/AIR7311 hardware attached** (`import uhd`
fails; no USRP-like USB device present). The user explicitly chose to
proceed anyway: write `EttusX440Adapter` and its tests now, with the actual
vendor-library calls isolated behind a small seam so everything else is
verified in this session, and leave the real cabled/attenuated hardware
verification for the user's lab. **The M9 exit criterion — actual
replay on real hardware — has not been met by this change.** It is a
required follow-up, not a formality.

## Decision

- **`UHDDevice` seam.** `agents/common/x440_adapter.py` defines a minimal
  `UHDDevice` Protocol (configure/read-back/send/end-burst/discover), sized
  to exactly what `EttusX440Adapter` calls. `_open_real_uhd_device` is the
  *only* function that does `import uhd`, done lazily inside the function
  body — not at module level — so importing `x440_adapter.py` (and
  therefore `agents/common/agent.py`, which every Agent process imports
  regardless of mode) never requires `uhd` to be installed. Tests inject a
  fake `UHDDevice` instead.
- **`uhd` is an optional dependency**
  (`pyproject.toml`'s `[project.optional-dependencies] x440`), not part of
  the base install — the control plane, simulated agents, and the test
  suite never need it. A real X440 Agent host installs with
  `pip install .[x440]` (ADR-004's bare-metal provisioning).
- **Real-TX safety gate at `start()`.** `settings.enable_real_tx`
  (`ROGUE_ENABLE_REAL_TX`, default `False`) is read by the Agent process
  itself — each Agent host gates its own hardware locally, independent of
  the control plane. `start()` raises `RealTxNotAuthorizedError` and never
  touches the device if this isn't explicitly set. This is a local,
  device-adapter-level interlock, separate from (and in addition to) the
  compiler's `SafetyPolicyOutcome.tx_authorized`, which stays the
  structural `False` placeholder ADR-007 introduced — a full policy engine
  remains a separate, later concern.
- **Single X440, single recording per channel, `cf32_le` only.**
  Multi-device capability-based scheduling is M10 by CLAUDE.md's own
  sequencing. A window whose composite channels reference more than one
  recording (two co-located links sharing an RF window) needs real
  baseband mixing to transmit correctly — not modelled here; `preflight`
  rejects that case with a clear error instead of transmitting something
  wrong. Only `cf32_le` recordings are accepted, matching UHD's native host
  format; other formats are rejected at `preflight`, not silently
  downsampled/converted.
- **No artificial looping or precise `end_seconds` alignment.** `start()`
  streams the cached recording once through, start to EOF, then ends the
  burst. Aligning exactly to the compiled window's `end_seconds` needs
  real clock-referenced timed commands (L3/L4 per `sdr-architecture.md`
  §5) — out of scope for this pass.
- **Compiler fix bundled into this milestone**: `OccupiedBand`/
  `CompositeChannel` gained a `recording: RecordingReference` field
  (`rogue/spectrum/models.py`, `rogue/compiler/models.py`), populated where
  the data was already resolved but previously discarded
  (`rogue/spectrum/occupancy.py`, `rogue/compiler/windows.py`). Without
  this, a real adapter had no way to know which cached SigMF asset to
  stream for a given physical channel — the compiled `ReplayPlan` only
  carried `emission_id`, not a resolved recording reference. This is a
  single, additive construction-site change (verified via grep: exactly
  one `OccupiedBand(...)`/`CompositeChannel(...)` call site each), not a
  breaking schema change. As a side effect,
  `rogue.execution.orchestrator.prepare_run` now sends each channel's
  `PREFLIGHT` command only the recording(s) that channel's window actually
  references, instead of M8's prior behaviour of sending every Agent the
  entire plan's `recording_manifest` regardless of relevance.

## Consequences

- `docs/architecture/implementation-plan.md`'s M9 row is marked "code
  complete, hardware-unverified," not "Done" — the actual exit criterion
  (cabled/attenuated replay on real hardware) needs a lab session this
  environment cannot provide. `docs/testing/manual-verification-guide.md`
  gains an M9 section written for the *user* to run in their lab, not
  something already confirmed here.
- `_open_real_uhd_device`'s exact UHD API calls (`MultiUSRP`, `StreamArgs`,
  `TuneRequest`, `TXMetadata`, range-object `.start()`/`.stop()` accessors)
  are written against UHD's documented Python API shape but not exercised
  against a real installation. UHD's Python API has had some naming/shape
  churn across releases — confirming and adjusting these calls against the
  actually-installed `uhd` version is the first thing a real lab run needs
  to do.
- Gain is a fixed default (`DEFAULT_GAIN_DB`); no power/gain policy is
  modelled. A reasonable follow-up once `RfWindow`/`CompositeChannel` carry
  an absolute gain target (today only `gain_offset_db`, which is relative).
- `DeepwaveAIR7311Adapter` (native SoapySDR, per ADR-005) is unaffected —
  still M10.
