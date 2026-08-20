# ADR-002: Hardware-Independent Canonical Scenarios

**Status:** Accepted baseline

## Decision
Canonical scenarios shall not persist bindings such as `Drone 1 -> AIR7311 #1`. They may express capability constraints or operator preferences. Actual SDR serial/channel/window assignments are generated during preparation and stored in the immutable run manifest.

## Rationale
This avoids vendor lock-in, allows runtime capability discovery, supports resource failure/reallocation policies and permits the same scenario to execute on different lab configurations.
