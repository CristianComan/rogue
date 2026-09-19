# ADR-016: Zone-Trigger Compiler Integration

**Status:** Accepted

## Context

ADR-015 added `RfEmission.zone_trigger` (an emission's active span derived from entering/
leaving a `TRIGGER`-typed `Zone`) and `DroneRfLink.observed_by_receiver_id`, but explicitly
scoped out compiler consumption: a `zone_trigger`-bearing emission validated cleanly but
`rogue.compiler.windows` had no way to turn it into an `RfWindow`, and
`observed_by_receiver_id` was dropped between `DroneRfLink` and `CompositeChannel`. This
ADR closes both gaps.

## Decision

### `observed_by_receiver_id`: straight passthrough

`rogue.spectrum.models.OccupiedBand` and `rogue.compiler.models.CompositeChannel` each
gain an `observed_by_receiver_id: UUID | None = None` field. Unlike the coherent-group
fields on the same two models (which need `rogue.compiler.coherent_groups.
expand_occupied_bands`'s geometry-aware expansion step), this is a straight copy —
`rogue.spectrum.occupancy.compute_spectrum_state` sets it directly from
`link.observed_by_receiver_id` when building each `OccupiedBand`, and
`rogue.compiler.windows.compute_rf_windows` copies it unchanged into each
`CompositeChannel`. No new geometry, no new finding.

### `zone_trigger`: two distinct sub-problems, two different costs

Resolving a `zone_trigger` emission's timing needs answering two different questions, at
two very different costs, so they're solved in two different places:

1. **"Is this emission active right now?"** — a point-in-time query, asked once per
   (link, boundary-instant) pair by `rogue.spectrum.occupancy.active_emission_at`
   (`compute_spectrum_state`'s inner loop). Answered directly with
   `point_in_polygon(evaluate_mission_position(mission, at_seconds), zone.polygon)` —
   O(1) per call.
2. **"Which instants matter at all?"** — a one-time, whole-horizon scan, done once per
   zone-triggered emission by `rogue.compiler.windows._boundary_seconds`. Answered with
   the existing `mission_evaluator.zone_crossings(mission, zone.polygon, 0.0,
   duration_s)` (interval-scanning, up to ~3600 samples), adding each interval's start/end
   to the boundary set.

Calling `zone_crossings` from the point-in-time path (or re-deriving the point query from
scratch inside the boundary-scanning path) would work but waste an order of magnitude of
computation for no benefit — this split is deliberate, not an oversight. `active_emission_at`
gained two new required parameters (`mission`, `zones_by_id`) to support the point query;
this is a public-function signature break, contained to `rogue.spectrum.occupancy` and its
own test file (its one production call site, inside the same module, was updated alongside
it — no HTTP API or cross-package caller exists).

### Unevaluable missions: default-deny, not a crash

`evaluate_mission_position`/`zone_crossings` raise `NotImplementedError` for a mission
template they don't cover (most templates besides `WAYPOINT_TRANSIT`/`SCRIPTED_TRACK`/
`ORBIT`) or a start policy not evaluable from scenario time alone (`ON_EVENT`/`MANUAL`).
Per CLAUDE.md rule 12 ("default deny TX"), a zone-triggered emission on such a mission is
treated as **never active** rather than always-on:

- In `active_emission_at`/`compute_spectrum_state`: the `NotImplementedError` is caught at
  the `compute_spectrum_state` call site, appended as a BLOCKING `SpectrumFinding`
  (`zone_trigger_position_unresolvable`), and that link contributes no occupied band for
  that instant — matching `rogue.compiler.coherent_groups.expand_occupied_bands`'s exact
  precedent for the same class of error.
- In `_boundary_seconds`: caught and reported as its own BLOCKING `CompilerFinding`
  (same code), returned alongside the boundary list (`_boundary_seconds` now returns
  `tuple[list[float], list[CompilerFinding]]`) — **not** silently skipped. An ultra code
  review caught the original version of this ADR's claim that
  `compute_spectrum_state` would independently catch the same error "at `t=0`/
  `t=duration_s`" as false: for a mission with a delayed `AT_TIME_OFFSET` start,
  `evaluate_mission_position`'s "before start" early return covers every boundary that
  survives when zone-trigger boundaries are the only interesting ones ({0.0, duration_s}),
  so the unsupported-template branch is never actually reached at either instant —
  producing no window *and* no finding, reproduced directly before the fix. Fixed by
  making `_boundary_seconds` report the finding itself rather than assuming a later stage
  will.

## Consequences

- Fully additive: both new model fields default to `None`, no migration, no schema break.
- `active_emission_at`'s signature change required updating 3 existing unit tests
  (`tests/unit/spectrum/test_occupancy.py`) to pass `mission`/`zones_by_id` — mechanical,
  no behavior change for non-zone-trigger callers.
- A `zone_trigger` emission on an unevaluable mission degrades to "never transmits" plus a
  BLOCKING finding, rather than either crashing the compile or (worse) transmitting
  unconditionally. This mirrors the coherent-group precedent exactly rather than
  inventing a new error-handling shape.
- `rogue.domain.validation._resolvable_span_seconds` (overlap detection) still skips
  zone-triggered emissions, as it already did per ADR-015 — this ADR doesn't add
  overlap-conflict detection between zone-triggered emissions and other spans on the same
  link. Left as a known, documented gap (same bucket as the existing looping-emission
  skip), not attempted here.
- Backend test suite grew: `tests/unit/spectrum/test_occupancy.py` (+9: zone-trigger
  point-query on/off/unresolvable-zone cases, `observed_by_receiver_id` passthrough, the
  unsupported-template BLOCKING-finding case) and `tests/unit/compiler/test_windows.py`
  (+4: a zone-triggered emission produces an `RfWindow` gated to its actual crossing
  interval rather than the full compile horizon, the same unsupported-template BLOCKING
  case surfacing through the compiler, that same case with a delayed `AT_TIME_OFFSET`
  mission start, `observed_by_receiver_id` surviving into `CompositeChannel`). `ruff`/
  `mypy` both pass on all changed files.

## Review findings not acted on

An ultra code review of this branch also raised two findings verified but not fixed here:

- `compute_rf_windows`'s window-coalescing step (extending an open window's
  `end_seconds` when center/bandwidth match) doesn't refresh `channels`, so a second
  emission on the same link that happens to land on the same frequency/bandwidth as the
  first can have its channel data silently dropped from the merged window. Reproduced
  directly, and confirmed present identically on `develop` *before* this branch — a
  pre-existing gap this PR's `observed_by_receiver_id` passthrough sits next to but did
  not introduce. Left for a separate, dedicated fix rather than folded in here.
- `active_emission_at`/`_boundary_seconds` resolve `zone_trigger.zone_id` via a plain
  dict lookup without re-checking the zone is `TRIGGER`-typed, relying entirely on
  `rogue.domain.validation.validate_scenario_version` having already rejected any other
  type at publish time. Verified this is safe in practice: `rogue.persistence.repository.
  publish_draft` already refuses to publish a `ScenarioVersion` with BLOCKING findings,
  and `compile_and_store_replay_plan` only ever compiles a published version — so this
  mirrors `array_group_id`'s exact existing precedent (also never re-checked in the
  compiler) rather than being a new gap.
