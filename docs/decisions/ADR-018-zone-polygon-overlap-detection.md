# ADR-018: Zone Polygon-Overlap Detection

**Status:** Accepted — closes the geometric half of ADR-017's remaining gap; the
time-domain half (zone-trigger vs. manually-timed overlap) is still open

## Context

ADR-017 added two BLOCKING `zone_trigger` overlap checks and explicitly left two cases
open: cross-zone geometric overlap (two *different* `TRIGGER` zones whose polygons
overlap in space) and zone-trigger-vs-manually-timed-emission overlap. This ADR closes
the first. It does **not** close the second: that one is fundamentally a time-domain
question (a manually-timed emission's `[start, end)` vs. whenever the mission happens to
be inside a zone, which needs `mission_evaluator.zone_crossings` over a compile horizon
`validate_scenario_version` doesn't have) — geometry alone can't answer it.

## Decision

### `rogue.domain.geometry.polygons_intersect`

A new primitive, `polygons_intersect(a: GeoPolygon, b: GeoPolygon) -> bool`, sitting next
to `point_in_polygon` with the same established conventions: exterior ring only
(`coordinates[0]`; interior rings/holes not modelled, matching every other consumer of
`GeoPolygon`), planar (lon, lat) treatment rather than geodesic (adequate at
scenario-authoring scale, not a claim of correctness for very large or pole-spanning
polygons), and 3D-ring-coordinate tolerant (same `(x, y, *_)` unpacking fix applied to
`point_in_polygon` earlier).

Handles arbitrary simple (non-self-intersecting) polygons, including concave ones, with
the standard two-part test: (1) every edge pair checked for a crossing via orientation/
cross-product tests, including the collinear-overlap and touching-endpoint cases — this
alone catches partial overlap and edge/vertex touching; (2) a single vertex-in-polygon
check each way (`point_in_polygon`) to catch full containment, where one polygon sits
entirely inside the other with no edges crossing at all. Touching-only (shared edge or
vertex, no interior overlap) is treated as intersecting — the conservative choice, since
this feeds a "flag a possible conflict" check, not a "prove definite safety" one.

### Severity: WARNING, not BLOCKING

Unlike ADR-017's two checks (duplicate `zone_id`, zone-trigger-vs-loop), which are
*provably certain* overlaps, two zone-triggered emissions on the same link referencing
different-but-spatially-overlapping zones are only a *possible* overlap — whether they're
ever simultaneously active depends on the mission's actual trajectory, which this
geometry-only check deliberately doesn't evaluate. New finding
`zone_trigger_zones_may_overlap` is WARNING, the same shape as `rogue.spectrum.
occupancy`'s `spectral_overlap` (advisory, since CLAUDE.md rule 5 makes intentional/
never-actually-realized overlap legal by default).

Scoped to the same link only (mirroring `overlapping_emissions`/
`zone_trigger_duplicate_zone`/`zone_trigger_overlaps_loop`'s existing precedent) —
independent links may legitimately overlap in time.

## Consequences

- New pure geometry primitive, fully covered by unit tests (disjoint, partial overlap,
  full containment either direction, identical polygons, edge-touching, vertex-touching,
  3D-ring coordinates).
- New WARNING finding code `zone_trigger_zones_may_overlap` — advisory only, never blocks
  publish. Existing scenarios are unaffected unless they happen to have two
  zone-triggered emissions on one link with overlapping zone geometry, in which case they
  now get a WARNING they didn't before (not a behavior break — WARNING findings were
  already a normal, non-blocking part of `validate_scenario_version`'s output).
- The zone-trigger-vs-manually-timed-emission overlap case remains open, still needing
  either a `duration_s` parameter threaded through `validate_scenario_version` or some
  other time-horizon source — tracked here as the one piece of ADR-017's original gap
  this ADR doesn't touch.
- Backend domain test suite grew by 9 tests: `tests/unit/domain/test_geometry.py` (+7:
  `polygons_intersect`'s disjoint/overlap/containment/identical/touching/3D cases) and
  `tests/unit/domain/test_validation.py` (+2 new, +1 existing test's assertions
  corrected: the disjoint-zones-no-warning case, the cross-link-not-flagged case, and
  fixing a stale comment/assertion on the existing different-zone-ids test that predates
  this primitive existing). `ruff`/`mypy` both pass.
