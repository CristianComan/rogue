"""RF spectrum planner (M5): deterministic spectrum state and conflict/headroom findings.

See docs/architecture/implementation-plan.md's M5 entry and
docs/architecture/rf-model.md section 5. This package computes spectrum
occupancy and conflict/headroom findings from *authored* scenario data at a
single scenario-time instant; it does not allocate RF windows/physical
channels or model RF power/clipping headroom — those are M6 Replay Plan
compiler concerns (see rogue.domain.rf's module docstring).
"""

from __future__ import annotations
