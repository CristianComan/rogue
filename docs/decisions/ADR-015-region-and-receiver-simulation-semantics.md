# ADR-015: Region and Receiver Simulation Semantics

**Status:** Accepted — domain model, reference-integrity validation and tests; compiler
integration unbuilt follow-up

## Context

M0-M14 are done or code-complete on `develop` (ADR-001 through ADR-014). Two gaps remained
in the domain model that later milestones' geometry/validation work had not yet closed:

1. **Zones were purely visual/advisory.** `Zone` (`OPERATIONAL_AREA`, `NO_TRANSMIT`,
   `NO_FLY`, `RESTRICTED`, `CUSTOM`) existed since M1 as area polygons, but nothing checked
   a mission's trajectory against a `NO_FLY` zone, and there was no way for a zone to drive
   RF timing (a "signal turns on when the drone enters this area" scenario).
2. **`DroneRfLink` had no notion of which receiver observes it.** `array_group_id`
   (ADR-012) exists for TDOA/AOA_DOA coherent-group *allocation*, but there was no
   equivalent for the much simpler case of a single `MONITOR` receiver that a planner
   wants recorded against a link, without that changing anything about how the link
   compiles.

Per CLAUDE.md rule 9 (`Receiver geometry is scenario data`) and rule 14 (`Determinism
matters` — mission/RF state must be computable from scenario time and fixed seeds), both
gaps belong in the domain model, evaluated the same deterministic way
`evaluate_mission_position` already is.

## Decision

### Point-in-polygon as a planar, ring-only primitive

`rogue.domain.geometry.point_in_polygon(point, polygon)` is a standard ray-casting test
against `GeoPolygon`'s first (exterior) ring, operating directly on (lon, lat) as a planar
ring — the same simplification MapLibre's own rendering already makes for these
zone/area polygons. This is adequate at the scenario-authoring scale ROGUE operates at
(city-block to city-scale areas), not a claim of geodesic correctness for very large or
pole-spanning polygons. Interior rings/holes are not modelled, matching every other
consumer of `GeoPolygon`. Ring points may be 2D or 3D (`GeoPosition2D | GeoPosition3D`);
the altitude component, if present, is ignored for containment.

### `zone_crossings`: one primitive, two consumers

`rogue.domain.mission_evaluator.zone_crossings(mission, polygon, window_start, window_end)`
samples `evaluate_mission_position` at a fixed ~1s cadence (`ZONE_CROSSING_STEP_SECONDS`,
capped at `MAX_ZONE_CROSSING_SAMPLES` samples) and returns the sub-intervals of
`[window_start, window_end)` where the mission is inside the polygon — the same
documented-approximation shape `rogue.compiler.coherent_groups.compute_doppler_schedule`
already uses for Doppler sampling (interval boundaries are reported at sampled
granularity, not sub-sample-interpolated crossing instants). This single primitive serves
two different semantics without two implementations:
- **`NO_FLY` containment** (mute/reject): the mission must never be inside the polygon.
- **`TRIGGER` zone emission timing** (turn on): the emission is active while inside the
  polygon.

`zone_crossings` propagates `NotImplementedError` from `evaluate_mission_position`
unchanged for mission templates the backend port doesn't evaluate yet — callers handle
that the same way `rogue.compiler.coherent_groups` already does for Doppler/phase/delay.

### `Zone.TRIGGER` and `RfEmission.zone_trigger`

A new `ZoneType.TRIGGER` value marks a zone as an emission timing source rather than a
visual/advisory annotation. `RfEmission.zone_trigger: ZoneTriggerPolicy | None` (holding
just `zone_id: UUID`) replaces `start_offset`/`duration_override` entirely when set —
enforced mutually exclusive by a model validator (a zone-triggered emission must have a
`recording`, and must not also set `duration_override`, a non-default `start_offset`, or
`loop`). Reference integrity (`zone_id` must resolve to a `TRIGGER`-typed `Zone` in the
same `ScenarioVersion`) is a cross-entity concern and lives in
`rogue.domain.validation.validate_scenario_version`, mirroring `array_group_id`'s own
precedent — `RfEmission`/`ZoneTriggerPolicy` alone don't know the scenario's zones.

### `DroneRfLink.observed_by_receiver_id`

A new optional field naming the single `MONITOR` receiver, if any, that "hears" this
link's emissions. It is orthogonal to `array_group_id` (TDOA/AOA_DOA coherent-group
allocation): purely informational for now, intended for a future planning sync
matrix / run channel display, and never changes channel count or allocation. Reference
integrity (must resolve to a `MONITOR`-type `Receiver`) is checked the same way as
`zone_trigger.zone_id`, in `validate_scenario_version`.

### `NO_FLY` containment check

`rogue.domain.validation._no_fly_containment_findings` is a new BLOCKING, plan-time
(publish) check: no mission's trajectory may enter a `NO_FLY` zone. Non-`ORBIT` templates
sample each waypoint-to-waypoint leg at five fixed fractions (endpoints + quarters) rather
than `zone_crossings`'s full sampling cadence — this only needs a yes/no containment
answer over the mission's whole authored span, not interval boundaries, so a coarser,
bounded sample per leg is enough. This is a documented approximation, not exact-geometry
segment/polygon intersection; a mission whose leg clips a thin sliver of a `NO_FLY` zone
between sample fractions would not be caught. Tightening this (adaptive sampling, or true
segment/polygon intersection) is possible future follow-up, not attempted here.

`ORBIT` is handled separately (`_orbit_no_fly_findings`): its two waypoints are a
center/radius reference, not path points, so chord-sampling between them checks the wrong
geometry entirely. It instead samples the real circular path via `zone_crossings`/
`evaluate_mission_position` over one full lap (`mission_evaluator.orbit_period_seconds` —
an orbit repeats identically forever, so one period is sufficient to observe the whole
path), and skips (rather than crashes) missions whose start policy isn't evaluable from
scenario time alone, matching `_resolvable_span_seconds`'s best-effort precedent.

Per-leg interpolation for the non-`ORBIT` path takes the shorter path across the +/-180
antimeridian (`_antimeridian_aware_lerp`) rather than naive linear longitude
interpolation, which would otherwise sweep the "long way" through longitude 0 for a short
hop across the date line and produce false-positive findings against zones nowhere near
the true path. A finding is emitted at most once per (mission leg, zone) pair — checked
across all sample fractions with `any()` — rather than once per matching fraction, so a
leg fully inside one zone is reported once, not five times.

## Consequences

- Fully additive to the M1 domain model: `ZoneType.TRIGGER` is a new enum value,
  `RfEmission.zone_trigger` and `DroneRfLink.observed_by_receiver_id` both default to
  `None`. No existing scenario document, schema version bump, or migration is required.
- **Compiler integration is explicitly not built here.** `rogue.compiler.windows` still
  only reads `start_offset`/`duration_override` when resolving an emission's span, and
  `rogue.compiler.models.CompositeChannel` does not carry `observed_by_receiver_id`
  through. A `zone_trigger`-bearing `RfEmission` will validate cleanly but the compiler
  cannot yet turn it into an `RfWindow`/`Allocation` — that is unbuilt follow-up work
  matching CLAUDE.md rule 13's "simulation/domain before hardware/execution" precedent,
  applied here as "domain semantics before compiler consumption."
- `_no_fly_containment_findings`'s five-fraction-per-leg sampling is a documented,
  bounded approximation (matching `zone_crossings`'s own approximation precedent), not a
  claim of exact geometric intersection.
- Backend domain test suite grew by 30 tests (93 -> 123): `tests/unit/domain/
  test_geometry.py` (point-in-polygon, including 3D-ring-coordinate handling),
  `test_mission_evaluator.py` (`zone_crossings` no-crossing / bounded-interior /
  open-ended-at-window-end / `NotImplementedError`-propagation cases, plus
  `orbit_period_seconds`), `test_rf.py` (`ZoneTriggerPolicy` mutual-exclusion
  validators, `observed_by_receiver_id` round-tripping), and `test_validation.py` (the
  two new reference-integrity finding functions plus `NO_FLY` containment for both
  straight-leg and `ORBIT` missions, the antimeridian case, and the one-finding-per-leg
  case). `ruff`/`mypy` both pass on all changed files.
- An ultra code review (multi-agent, run against this branch before merge) found and
  reproduced three real defects in the first version of `_no_fly_containment_findings`:
  `ORBIT` missions checked against the wrong geometry (the raw waypoint chord instead of
  the actual circular path), a naive-longitude-interpolation antimeridian bug producing
  false positives, and a `break` that only escaped the inner per-zone loop, producing one
  duplicate finding per sample fraction instead of one per violation. All three are fixed
  as described above and locked in by the added regression tests, discovered and
  addressed within this same ADR/branch rather than shipped and fixed later.
