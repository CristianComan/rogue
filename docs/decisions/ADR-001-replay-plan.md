# ADR-001: Replay Plan as Execution Boundary

**Status:** Accepted baseline

## Context
Scenarios must remain reusable across different laboratory hardware topologies while execution requires exact SDR/channel, frequency, timing and DSP instructions.

## Decision
Introduce an immutable Replay Plan (stored with the run manifest) between Scenario and SDR execution.

```text
Scenario -> RF Environment Compiler -> Replay Plan -> SDR Agents
```

The compiler resolves realized frequency events, RF windows, composite emissions, physical allocations, timing, gain, Doppler, delay/phase and validation expectations.

## Consequences
- scenario remains hardware-independent;
- allocation can change between runs without changing scenario intent;
- run execution is reproducible/auditable;
- compiler becomes a critical deterministic component requiring extensive tests.
