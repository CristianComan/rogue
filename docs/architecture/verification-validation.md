# ROGUE Verification and Validation Strategy

## 1. Objective

Verification proves that software components satisfy their contracts. Validation proves that a ROGUE run generated the intended RF environment and retained sufficient evidence to reproduce and assess it.

## 2. Test layers

| Layer | Coverage |
|---|---|
| Domain/unit | mission generation, time evaluation, validation, state transitions, allocation, RF planning/policy |
| API/contract | OpenAPI/schema, permissions, idempotency, optimistic locking, UI/API/agent compatibility |
| Simulation integration | virtual agents, message loss/delay, clock drift, cache failure, restart, abort |
| Hardware adapter | discovery, readback, replay, underrun, stop/watchdog, recovery |
| HIL acceptance | cabled/attenuated replay, measured start offset, multi-device alignment, emergency stop, evidence |
| UI end-to-end | create → validate → prepare → arm → run → abort/complete → review/export |
| Security | RBAC, credential expiry, replayed/stale commands, malformed assets, unauthorized TX, audit integrity |

## 3. Readiness validation

Before ARM, validate:
- JSON/schema and references;
- mission geometry, timing and kinematics;
- SigMF pairing, checksum, duration and metadata;
- RF window placement, guard margins and switching events;
- sample rate/bandwidth/gain/power compatibility;
- composite peak/RMS/headroom and clipping/backoff policy;
- channel/resource conflicts;
- inter-band hardware capability/converter chain;
- agent health/version/cache/disk;
- clock quality against run requirement;
- transmit policy and operator authorization.

Findings are machine-readable with code, severity, object path, explanation and remediation, plus a human-readable readiness report. Blocking findings prevent ARM.

## 4. Independent RF validation

The RF monitor is independent of the replay command path. For each relevant window/run, compare measurement to the compiled Replay Plan and record:
- occupied center frequency/frequencies;
- bandwidth;
- spectral overlap;
- relative/absolute power where calibrated;
- start/stop timing;
- relative delay/alignment;
- phase/coherence where required for AOA/DOA;
- underrun/discontinuity indicators.

Validation evidence is attached to the immutable run record.

## 5. Required RF scheduler scenarios

At minimum test:
1. four drones sharing 2.4 GHz at different/overlapping frequencies;
2. one drone hopping among 2.4-GHz channels without LO retune;
3. one drone switching 2.4 → 5.8 GHz and migrating hardware;
4. intentional spectral overlap;
5. insufficient instantaneous bandwidth;
6. clipping/headroom warning;
7. loss of a physical channel causing deterministic failure or policy-permitted reallocation.

## 6. MVP acceptance scenarios

- Designer creates two missions, associates two SigMF recordings, validates and publishes version 1.
- Test director prepares two simulated SDR resources, arms and starts a run.
- Live console shows both tracks and replay progress; deliberate stop is recorded.
- Agent disconnect causes watchdog stop and FAILED/ABORTED according to policy with complete evidence.
- Same immutable version/recordings can be rerun and compared.
- Real SDR performs only explicitly gated cabled/attenuated replay and emergency stop is verified.
