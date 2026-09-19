# ADR-014: Independent RF Validation

**Status:** Accepted — domain, comparison, simulated-monitor and orchestration slice; real
capture hardware unverified

## Context

M0-M13 are done or code-complete on `develop`. M14 — independent RF validation — is the
last milestone in CLAUDE.md §13's explicit sequence and had no code at all
(`implementation-plan.md`: "Planned"). Per CLAUDE.md rule 15, `rf-model.md` §9 and
`verification-validation.md` §4: an RF monitor must be independent of the replay command
path — it observes what a run actually produced and compares it to the compiled
`ReplayPlan`, rather than asking the TX `SDRAdapter` to self-report — and the result is
attached to the immutable `ScenarioRun` as append-only evidence (`domain-model.md` §5).

**Does this need real capture hardware (spectrum analyzer, RX-SDR loopback)?** No, and
none is attached in this environment. Per CLAUDE.md rule 13 ("simulation comes before
hardware") and `sdr-architecture.md` §8's "not a throwaway mock" precedent (already
applied to `MockSDRAdapter`, `EttusX440Adapter`/`DeepwaveAIR7311Adapter`'s simulated
predecessor), this slice builds a first-class simulated `RfMonitorAdapter` and the full
capture->compare->evidence pipeline around it. Real capture hardware is a later, optional
pass, matching M9/M10/M12/M13's "code complete, hardware-unverified" precedent exactly —
not attempted or claimed here.

## Decision

### Architectural independence from the TX path

`rogue.validation` is a new top-level package with no import or state dependency on
`rogue.execution` beyond reusing one plain exception class
(`InvalidRunTransitionError`, for consistent run-lifecycle error handling — the same
kind of reuse M8 did for `AdapterOperationError` across two `SDRAdapter`
implementations). `rogue.validation.monitor_adapter.RfMonitorAdapter` is a distinct
`Protocol` from `rogue.execution.adapter.SDRAdapter`; `MockRfMonitorAdapter` shares no
code or state with `MockSDRAdapter`, and `rogue.persistence.run` holds them as two
separate module-level singletons (`_ADAPTER` vs `_MONITOR_ADAPTER`). A real
implementation (spectrum analyzer, RX-SDR loopback) would plug into
`RfMonitorAdapter.capture()` without either the TX adapters or `rogue.execution`
changing at all.

### Explicit-instant capture, not continuous monitoring

`rogue.validation.orchestrator.run_validation(run, plan, receivers, monitor_adapter,
at_seconds)` captures every relevant `Receiver` at one explicit scenario-time instant —
mirrors M5's `at_seconds`/M6's `duration_s` explicit-horizon precedent rather than
building a new live-streaming monitor loop. `MONITOR` receivers are captured against
every `RfWindow` active at `at_seconds`; `TDOA`/`AOA_DOA` receivers are captured only
against the specific `CompositeChannel`(s) whose `array_element_receiver_id` matches
them (additionally comparing `delay_offset_s`/`phase_offset_rad`). A receiver with
nothing active at `at_seconds` (e.g. a MONITOR receiver during a silent span)
contributes no report — that is not an error, just nothing to validate right now. The
one exception: a `TDOA`/`AOA_DOA` receiver that the compiled plan never gave *any*
coherent-group coverage to at all (e.g. `rogue.compiler.coherent_groups`'s
reference-integrity fallback degraded the link to non-coherent) always produces a
BLOCKING `window_not_found` finding, independent of `at_seconds` — a real,
always-computable gap distinct from "not currently transmitting."

### Comparison and evidence shape

`rogue.validation.compare.compare_measurement_to_plan` is pure (no I/O), mirroring
`rogue.spectrum.occupancy`/`rogue.compiler.windows`'s shape, and reuses
`rogue.domain.validation.ValidationSeverity` rather than a third severity enum.
Tolerance constants (`FREQUENCY_TOLERANCE_HZ=5kHz`, `BANDWIDTH_TOLERANCE_RATIO=5%`,
`TIMING_TOLERANCE_S=0.2s`, `DELAY_TOLERANCE_S=1us`, `PHASE_TOLERANCE_RAD=0.05rad`) are
reasonable defaults for a simulated monitor, not a calibrated instrument
specification — a real capture implementation would need its own, measured tolerances.
Underrun/discontinuity and delay/phase deviations are BLOCKING (safety/coherence-
critical); frequency deviation is BLOCKING (wrong-channel is a hard failure); bandwidth
and timing deviations are WARNING (softer, expected to have more natural jitter).

`RfMeasurement`/`RfValidationReport`/`RfValidationFinding` (`rogue.domain.rf_validation`)
are additive; `ScenarioRun.validation_reports: list[RfValidationReport]` is a new
append-only field (JSONB-additive, no migration — same pattern as M8's
`DeviceLease.expires_at` and M11's `required_sync_class`). A new
`RunEventKind.VALIDATION_RECORDED` event is appended alongside each report, carrying
the aggregate severity (BLOCKING if any finding is BLOCKING, WARNING otherwise), so the
existing `events` audit trail stays a complete summary without needing to inspect
`validation_reports` separately.

### Simulated monitor's ground truth

`MockRfMonitorAdapter.capture()` reads the plan's *declared* window/channel values as
ground truth — the only ground truth a *simulated* capture can have — and injects a
small deterministic bounded jitter, seeded from `(receiver.id, window.window_key,
at_seconds)` so repeated captures of the same instant are reproducible
(`random.Random(str)` is deterministic across processes regardless of
`PYTHONHASHSEED`, unlike a plain tuple hash). `force_deviation_hz`/`force_underrun`
let a test push a specific `(receiver_id, window_key)` capture outside tolerance on
demand, mirroring `MockSDRAdapter.fail_on`'s precedent. This makes `compare.py` exercise
real, non-tautological signal rather than an always-pass echo — but it is a genuinely
different limitation from a future real capture device, which is the actual point of
keeping `RfMonitorAdapter` a clean seam.

### API

`POST /scenarios/{id}/replay-plans/{plan_id}/runs/{run_id}/validate` (body:
`{"at_seconds": float}`, idempotency-key-wrapped like arm/start/stop, 200) triggers one
capture pass and returns the full updated `ScenarioRun`. No new GET endpoint — the
existing `GET .../runs/{run_id}` already returns the whole `ScenarioRun`, so
`validation_reports` is visible there once populated. Requires the run to be `RUNNING`
or `STOPPED` (`InvalidRunTransitionError`, already mapped to HTTP 409).

## Consequences

- Fully additive: `validation_reports` defaults to `[]`, no existing `ScenarioRun`/API
  behavior changes, no migration needed.
- Real spectrum-analyzer/RX-SDR hardware integration, calibrated absolute power, and any
  frontend UI are explicitly out of scope here (M11-M13 set the "backend-only milestone"
  precedent; `validation_reports` is already visible via the existing run-fetch endpoint
  for a future UI to consume) — tracked as future, optional passes, not attempted or
  claimed in this ADR.
- Feeding validation results back into control decisions (auto-abort on a BLOCKING
  finding, etc.) is explicitly not built here, per rule 15 — this stays a
  reporting/evidence path only; a future policy layer would be a separate, later
  decision.
- `MockRfMonitorAdapter`'s "ground truth is the plan itself, plus injected jitter" is a
  documented simulation limitation, not a claim that the independent-validation
  architecture is a tautology — the whole point of the `RfMonitorAdapter` seam is that a
  real device's genuinely independent observation slots into the same `capture()`
  contract without touching `compare.py`, the orchestrator, persistence or the API.
