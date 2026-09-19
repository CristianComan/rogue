# ADR-017: Zone-Trigger Overlap Detection (Partial)

**Status:** Accepted — the two statically-provable cases only; cross-zone geometric
overlap and zone-trigger-vs-manually-timed overlap remain open

## Context

`rogue.domain.validation._resolvable_span_seconds` (the input to the existing
`overlapping_emissions` check) returns `None` — i.e. "skip this emission" — for any
`zone_trigger` emission, since it has no `start_offset`/`duration_override` to read
(both fixed at their defaults by `RfEmission`'s own mutual-exclusion validator, per
ADR-015). ADR-016 flagged this as a known, documented gap rather than fixing it. This
ADR closes the part of that gap that's actually checkable today.

**Why not the whole gap?** `validate_scenario_version(version)` takes no
`duration_s`/compile-horizon parameter — unlike `rogue.compiler.windows.
compute_rf_windows`, there's no scenario-wide time bound to scan
`mission_evaluator.zone_crossings` against at the domain-validation layer. And there is
no polygon-intersection primitive in the codebase — only `rogue.domain.geometry.
point_in_polygon` (point-vs-polygon, not polygon-vs-polygon). Both would be needed to
detect the general case (two *different* zones whose polygons overlap in space, or a
zone-triggered emission against a manually-timed non-looping one) and neither is a small
addition — adding a duration parameter would ripple through `validate_scenario_version`'s
signature and every caller; a robust polygon-intersection routine is a real geometry
investment, not a documented-approximation shortcut in the spirit of this module's
existing ones (`point_in_polygon`'s planar ring simplification, `zone_crossings`'s ~1s
sampling cadence, the `NO_FLY` check's five-fraction-per-leg sampling).

## Decision

`rogue.domain.validation._zone_trigger_overlap_findings` adds two new BLOCKING checks,
each provable with zero new geometry and no time-horizon parameter:

1. **Duplicate `zone_id`** (`zone_trigger_duplicate_zone`): two `zone_trigger` emissions
   on the same `DroneRfLink` referencing the *same* zone activate/deactivate in lockstep
   — they always overlap, by construction, regardless of the zone's actual shape or the
   mission's trajectory.
2. **Zone-trigger vs. loop** (`zone_trigger_overlaps_loop`): a `zone_trigger` emission
   coexisting on a link with a `loop=True` emission always overlaps it — a looping
   emission is active for the entire scenario by definition (the same "open-ended by
   design" reasoning `_resolvable_span_seconds`'s own docstring already gives for
   skipping loop emissions from the general check).

Both are simple set/flag checks over `link.emissions`, no `mission_evaluator` or
`geometry` calls needed — they follow the exact same "reference-integrity-shaped, not
geometry-shaped" style as `_zone_reference_findings`.

## Consequences

- Two new BLOCKING finding codes: `zone_trigger_duplicate_zone`,
  `zone_trigger_overlaps_loop`. Fully additive — no schema change, existing valid
  scenarios are unaffected (verified: the full pre-existing domain test suite still
  passes with zero new findings on any prior fixture).
- **Still open, not attempted here**: two zone-triggered emissions on the same link
  referencing *different* zones whose polygons happen to overlap in space (would need a
  polygon-intersection primitive), and a zone-triggered emission overlapping a
  manually-timed non-looping emission on the same link (would need a compile-horizon
  parameter threaded through `validate_scenario_version`). Both remain exactly the gap
  ADR-016 originally flagged, just narrowed — not silently dropped, tracked here for
  whichever of the two prerequisites (polygon intersection, or a validation-time
  duration_s) becomes needed for other reasons first.
- Backend domain test suite grew by 3 tests (126 total in `tests/unit/domain`):
  `test_validation.py` — duplicate-zone BLOCKING, zone-trigger-vs-loop BLOCKING, and a
  negative case (two *different* zone_ids, no loop, not blocking — confirming the
  narrow scope is respected even when both zones happen to share an identical polygon).
  `ruff`/`mypy` both pass.
