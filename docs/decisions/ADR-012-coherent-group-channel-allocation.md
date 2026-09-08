# ADR-012: Coherent-Group RF Window Generation and Atomic Channel Allocation

**Status:** Accepted baseline — domain + compiler slice only

## Context

`Receiver.array_group_id` (M1) declares that a set of TDOA/AOA_DOA receiver
elements must be jointly time/phase-synchronized by the compiler
(rf-model.md section 6), but per ADR-006's own closing note, `Receiver`
geometry was never consumed by the M6 compiler at all — `array_group_id`
existed only as a receiver-side clustering key with no bridge to any
`DroneRfLink`/`RfWindow`/`Allocation`. Per `implementation-plan.md`'s
milestone table this spans three separate planned milestones (M11 Multi-SDR
synchronization, M12 Doppler/delay/phase, M13 TDOA/AOA receiver
stimulation), none started, and no formula existed anywhere in the repo for
AOA/DOA phase (rf-model.md section 6 gives a formula for TDOA delay only,
explicitly hedged as "conceptual").

Given the size, this ADR and its implementation cover the **domain +
compiler slice only**: producing a compiled `ReplayPlan` that correctly
expresses coherent-group channel allocation with computed Δφ/τ, entirely in
the pure/deterministic compiler layer. Real-time DSP application of the
phase/delay schedule during streaming (continuous NCO/delay) and
cross-Agent synchronized arm/start/mute remain out of scope, tracked as
execution-layer follow-ups.

## Decision

**Domain link** (`rogue.domain.rf.DroneRfLink.array_group_id`, optional,
additive): a link declares which `Receiver.array_group_id` it must be
coherently synthesized for. Reference integrity (must resolve to >=2
TDOA/AOA_DOA receivers) is a new cross-entity check in
`rogue.domain.validation.validate_scenario_version`
(`coherent_group_unresolvable`, BLOCKING).

**Mission-position infrastructure** (`rogue.domain.geometry`,
`rogue.domain.mission_evaluator`, new): the compiler needs the
transmitter's position `p_tx(t)` to compute receiver-relative phase/delay,
which nothing on the backend could do before now — `rogue.domain.mission`'s
own docstring explicitly deferred mission-time evaluation to "the mission
engine," which so far only existed on the frontend
(`missionEvaluator.ts`). `mission_evaluator.py` is a narrow backend port
(WAYPOINT_TRANSIT/SCRIPTED_TRACK arc-length interpolation, ORBIT angular
motion only; other templates raise `NotImplementedError` naming the gap),
using the same haversine/bearing math as the frontend
(`rogue.domain.geometry`) so both sides agree numerically.

**Geometry math** (`rogue.compiler.coherent_groups`, new — no existing
formula to transcribe beyond TDOA's conceptual one):
- Reference element: deterministic, the group's lowest `element_index`
  (missing indices sort last, tie-broken by receiver id) — `element_index`
  is optional even on array-type receivers today, so this can't assume it's
  always populated.
- Delay: `Δτ = (|p_tx - p_element| - |p_tx - p_reference|) / c`, per
  rf-model.md section 6's formula, relative to the reference element.
- Phase (AOA_DOA only — TDOA elements have no `element_local_offset_m`):
  project `element_local_offset_m - reference_local_offset_m` onto the
  horizontal line-of-sight unit vector from the reference position to
  `p_tx(t)`, `phase = 2π/λ · projected_offset_m`. This sign convention and
  the horizontal-only (no elevation) simplification are **new design
  choices**, not a transcription of any existing spec — rf-model.md gives
  no AOA/DOA formula at all.
- Computed **once per `RfWindow` span, at the span's `start_seconds`** — a
  piecewise-constant approximation, not a continuous per-sample schedule.
  Continuous application during streaming is explicitly out of scope
  (execution-layer, M12).

**Window generation** (`rogue.compiler.windows`): a coherent link's
occupied band is expanded into one band per target `Receiver` element
before packing. Two elements of the same `coherent_group_id` are never
packed into the same `RfWindow` even though they're frequency-identical —
unlike ADR-003's normal same-channel sharing, they must land on *different*
physical channels simultaneously. Each element's `window_key` folds in the
target receiver id so per-element window identity stays stable and unique
across time spans, preserving the existing "sticky assignment" allocator
cache for the non-coherent case unchanged.

**Atomic allocation** (`rogue.compiler.allocation`): windows sharing one
non-null `coherent_group_id` at the same time span are allocated as one
unit — every member gets a distinct free/capable channel together, or
**none** of them do (`insufficient_physical_channels_for_coherent_group`,
BLOCKING), never a partial group. Independent (non-coherent) windows are
allocated exactly as before ADR-006; this ADR only adds a new code path
alongside the existing one.

## Consequences

- Deterministic and unit-testable (`tests/unit/domain/`,
  `tests/unit/compiler/`), matching rule 14.
- Additive/optional fields only (`CompositeChannel.coherent_group_id`/
  `array_element_receiver_id`/`phase_offset_rad`/`delay_offset_s`,
  `OccupiedBand`'s same four) — no existing `Allocation`, `ReplayPlan`, or
  non-coherent `CompositeChannel` shape changes; a scenario with no
  `array_group_id` links compiles identically to before this ADR.
- Horizontal-only geometry (no elevation/altitude in the phase/delay
  projection) is a known simplification of this first slice, not a
  permanent design constraint.
- Explicitly **not** touched: `rogue.execution.orchestrator`/
  `lease_sweep`, `rogue.protocol.messages`, `agents/common/*`, any vendor
  adapter — no group-aware lease/arm/start/stop, no NATS protocol changes,
  no multi-channel UHD streaming. A compiled plan expressing a coherent
  group does not yet mean the run orchestrator executes it as one atomic
  unit; that is tracked as a future execution-layer slice.
- Continuous (per-sample) Doppler/delay/phase application during actual
  streaming remains M12/execution-layer work, not addressed here.
