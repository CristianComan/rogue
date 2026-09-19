# ADR-006: RF Window Packing and Physical Channel Allocation Algorithm (M6)

**Status:** Accepted baseline

## Context

ADR-003 establishes that multiple logical emissions may share one physical
TX channel's usable bandwidth ("RF window"), and rf-model.md section 5
requires the compiler to "preserve intentional spectral overlap," "enforce
usable bandwidth and guard margins" and "detect impossible placement" — but
neither document specifies an algorithm. M6 (`backend/rogue/compiler/`)
needed one concrete, deterministic, testable choice to compile a
`ScenarioVersion` into an executable `ReplayPlan`.

## Decision

**Window packing** (`rogue.compiler.windows`): at each instant occupancy
can change (a realized frequency event or an emission start/end boundary),
reuse M5's `compute_spectrum_state` to get the occupied bands at that
instant, sort them by `freq_min_hz`, and greedily merge adjacent bands into
one window while the group's total span stays within
`DEFAULT_GUARD_MARGIN_HZ` (100 kHz) of each other and within the widest
configured physical channel's `max_usable_bandwidth_hz`. A window's
identity (`window_key`) across time is the sorted set of link IDs
currently occupying it — a simple, deterministic scheme that gives the
allocator continuity when membership is unchanged, and naturally forces a
new window identity when it changes. Adjacent instants producing an
identical window set are coalesced into one time span.

**Channel allocation** (`rogue.compiler.allocation`): first-fit. Each
window span tries to keep its previous physical channel (if still free and
still tunable to the new center/bandwidth); otherwise it takes the first
free, capable channel in `capability_profile.channels` order, marked as a
migration. No cost-optimal reassignment and no cross-channel aggregate-
power/intermodulation check.

**Default capability profile** (`rogue.compiler.models.
DEFAULT_CAPABILITY_PROFILE`): illustrative numbers matching CLAUDE.md
section 4's 24-channel initial planning profile — 2× `x440-{1,2}` × 8
channels (`tunable_ranges_hz` excludes 5.15-5.925 GHz per CLAUDE.md rule 4;
400 MHz usable bandwidth, 500 Msps), 2× `air7311-{1,2}` × 4 channels
(covers 70 MHz-6 GHz including the band X440 can't natively reach; 100 MHz
usable bandwidth, 125 Msps). These are compile-time defaults, not
runtime-discovered hardware (rule 10) — real numbers replace this once M8/
M10 add capability readback; a caller may already override the whole
profile per compile request.

## Consequences

- Deterministic and unit-testable (`tests/unit/compiler/`), matching rule
  14.
- Conservative: a scenario that a smarter scheduler could pack more
  tightly may report `insufficient_physical_channels` here. Acceptable for
  M6's "produces *a* correct, hardware-neutral plan" goal; a better
  scheduler is a future increment, not a blocker.
- Explicitly **not** modelled: aggregate peak/RMS/clipping-risk/backoff and
  intermodulation-risk assessment (rf-model.md section 5's other bullets) —
  these need actual I/Q amplitude modeling, which belongs at execution time
  (M7+), not static compilation. `SafetyPolicyOutcome.tx_authorized`
  defaults to `False` unconditionally (rule 12) — a compiled plan never
  authorizes transmission by itself.
- Doppler/delay/phase (M12) and TDOA/AOA per-receiver stream generation
  (M13) are out of scope; `Receiver` geometry is not consumed by the M6
  compiler at all.
