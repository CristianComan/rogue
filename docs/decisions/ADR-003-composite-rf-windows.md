# ADR-003: Physical TX Channels as Composite RF Windows

**Status:** Accepted baseline

## Decision
Treat each physical SDR TX channel as a wideband RF canvas/window. Multiple logical emissions may be independently resampled, translated, scaled, Doppler/delay/phase adjusted and complex-summed when they fit the usable bandwidth and policy constraints.

Intentional spectral overlap is allowed. Validation focuses on placement feasibility, guard margins, aggregate power, peak/RMS headroom, clipping risk and hardware limits.

## Consequences
This supports realistic multi-drone spectrum occupancy and intra-band channel search/switching without consuming one physical TX channel per logical emission.
