# ADR-013: Multi-SDR Synchronized Barrier Start and Continuous Doppler/Delay/Phase Execution

**Status:** Accepted — execution-layer slice, software-barrier (L1) only

## Context

ADR-012 built the **domain + compiler slice only** for coherent-group TDOA/AOA_DOA
support and explicitly deferred two things as "execution-layer follow-ups": **(M11)**
cross-Agent synchronized arm/start, and **(M12)** continuous (not piecewise-constant)
application of the compiled Doppler/delay/phase schedule during actual streaming. This
ADR picks up both, plus a related, closely-coupled capability: relaxing ADR-009's
original one-recording-per-physical-channel restriction to N-way mixing, since
completing M12's DSP pipeline meant the streaming code had to be touched anyway, and
the domain model (`RfWindow.channels: list[CompositeChannel]`, ADR-003) has supported
more than one composite channel per physical channel since M6 — only the M9/M10 real
adapters ever refused to exercise it.

**Does this need real AIR7311 (or X440) hardware turned on?** No. Neither
`EttusX440Adapter` nor `DeepwaveAIR7311Adapter` exposes any PPS/PTP/timed-command
capability today (`agents/common/sdr_adapter_base.py`), so per `sdr-architecture.md`
§5's timing-class table, L3 ("shared PPS/10 MHz or hardware PTP + timed commands") and
L4 ("L3 + reference/loopback measurement") are not achievable regardless of what
hardware is powered on — there is no code path anywhere that would use such a feature
even if it were present. What this slice builds and demonstrates is **L1 (NTP hosts +
software barrier)**, entirely in software, fully exercisable against `MockSDRAdapter`
plus the existing 2-simulated-agent docker-compose setup (CLAUDE.md rule 13:
"simulation comes before hardware... testable with simulated agents"). If real-hardware
verification of the DSP pipeline is wanted later, `StreamingSDRAdapter` is the shared
base both real adapters already subclass, so it needs no further code changes — that
would be a separate, later, optional pass, matching M9/M10's "code complete,
hardware-unverified" precedent, not part of this slice.

## Decision

### M11 — synchronized barrier start, measured

`ReplayPlan.required_sync_class: TimingSyncClass` (new, default `L0_SIMULATED`) is the
strictest `ResourcePreference.required_sync_class` declared by any `DroneRfLink` in the
version (`rogue.compiler.compile._required_sync_class`). Requesting L3/L4 gets one
`CompilerFinding(code="sync_class_not_achievable", severity=WARNING)` — a capability
gap, not a scenario error, so it never blocks compilation.

`rogue.execution.orchestrator.start_run`: an `L0_SIMULATED` plan's behavior is
byte-for-byte unchanged (the original sequential per-channel loop, extracted verbatim
into `_start_sequential`). Anything stricter runs `_start_with_barrier`: every channel's
`adapter.start(device_id, channel_index, barrier_at=barrier_at)` is issued concurrently
(`asyncio.gather`) with one shared future timestamp, then — after sleeping past it — each
channel's `status()` is polled for `actual_tx_start_at` to compute the achieved skew,
recorded as a new `RunEventKind.SYNC_MEASURED` event. This is always executed as L1
regardless of whether L1, L2, L3 or L4 was requested (L2's "scheduled local future
start" and L1's "software barrier" are the same mechanism from this system's
distributed-Agent perspective; L3/L4 aren't attempted, per the capability gap above). A
channel that hasn't reported an actual start time by the settle deadline is a WARNING
event, not a run failure — that's telemetry precision, not a safety gate; a channel
whose barrier-scheduled start itself failed (`status().last_error` set) still fails the
run, exactly like every other per-channel operation failure already does.

**Why `start()` must return once scheduled, not once it fires** — a correctness
requirement, not a style choice, found while reading `agents/common/agent.py`: its
command loop (`_command_loop`) processes one NATS message at a time, fully awaiting
each command's handler before the next. If a barrier-scheduled `start()` awaited its own
`asyncio.sleep` before returning, a second channel owned by the *same* Agent would only
begin *its own* wait once the first's had already elapsed — breaking the barrier for
every multi-channel Agent, which is the common case (each Agent typically owns several
channels of one physical unit). So every `SDRAdapter.start()` implementation
(`MockSDRAdapter`, `StreamingSDRAdapter`) schedules the actual keying as a background
task and returns immediately once it's scheduled — the same fire-and-forget pattern
`StreamingSDRAdapter` already used for its streaming task, just applied one layer
earlier. A failure inside that background task can't be raised back to the original
caller (it already returned), so it's recorded on `AdapterDeviceStatus.last_error`
instead, polled by `_start_with_barrier` after the settle wait.

Protocol/adapter surface, entirely additive (`None`-defaulted, every existing call site
and test unaffected): `SDRAdapter.start(..., barrier_at: datetime | None = None)`,
`AdapterDeviceStatus.{actual_tx_start_at, last_error}`, `AgentCommand.barrier_at`.

### M12 — continuous Doppler-driven phase during streaming

Scoped to **coherent-group channels only** — the only place a compiled channel is
associated with a specific receiver/geometry relationship at all today. A MONITOR
receiver has no such link (it isn't a "group"), and inventing one is a separate, larger
domain-modeling question outside "pick up ADR-012's own deferred follow-up." Delay stays
**piecewise-constant per window**, unchanged from ADR-012 — at realistic drone speeds it
changes by a negligible sub-sample amount within one window's span, so continuously
tracking it would add real complexity (a time-varying resampler) for no measurable
benefit at this scale. Doppler-driven phase is different: applying it as anything other
than a continuous, phase-accumulating NCO would be physically meaningless (a discrete
per-window frequency jump), and CLAUDE.md rule 9 explicitly calls for "numerically
stable NCO/phase accumulation."

`rogue.compiler.coherent_groups.compute_doppler_schedule(receiver, mission,
window_start, window_end, carrier_hz)` samples `evaluate_mission_position` at a ~1s
cadence (capped at `MAX_DOPPLER_SCHEDULE_SAMPLES` for very long windows), finite-
differences range to get range-rate (the same two-sample technique as the frontend's
`domain/doppler.ts:rangeAndRangeRate`), and converts via `doppler_shift_hz =
-range_rate_mps / c * carrier_hz` — closing (negative range-rate) yields a *positive*
(blue) shift, receding yields negative (red) — the standard physics convention, which is
the **opposite sign** from the frontend's own "positive range-rate = receding"
convention for range-rate itself (only the shift's sign is flipped; range-rate's
convention is shared and unchanged). Computed for **both** TDOA and AOA_DOA elements —
Doppler needs no `element_local_offset_m`, unlike phase.

Unlike phase/delay, this is **not** computed inline in `expand_occupied_bands` at each
packing instant: `rogue.compiler.windows`'s window-coalescing can extend an already-open
window's `end_seconds` across several packing instants without recomputing its
channels, so only a later pass over each window's *final* span
(`windows.py:_attach_doppler_schedules`, run once `compute_rf_windows` has finished
coalescing) can correctly span the whole thing. `CompositeChannel.doppler_schedule:
list[DopplerSample] | None` carries the result (additive, alongside the existing four
coherent-group fields).

`agents/common/dsp.py` (new, pure, no device/NATS dependency — exercised entirely with
synthetic signals in `tests/unit/agents/test_dsp.py`, no real SDR hardware needed):
`PhaseAccumulatorNCO` (a stateful phase accumulator so consecutive `generate()` calls
stay phase-continuous even as the interpolated Doppler value changes between them —
the "numerically stable" part of rule 9), `interpolate_doppler_hz` (linear, clamped at
the schedule's bounds), and `FractionalDelayLine` (a linear-interpolation fractional-
sample delay with one sample of cross-chunk history — a documented simplification
versus a full polyphase/Farrow filter, adequate at the sub-microsecond delays typical of
a compact receiver array; a future refinement, not a hidden gap).
`CoherentChannelDSPState` combines both, tracking one channel's elapsed stream-local
time so it never needs further control-plane contact mid-burst (`sdr-architecture.md`
§6: "the control network is not the sample transport path").

### Multiple recordings per physical channel

`StreamingSDRAdapter.preflight()`'s `len(recordings) != 1` rejection becomes `< 1`: it
now pairs each `RfWindow.channels[i]` (by its `recording: RecordingReference`) to its
resolved `IQRecording`, giving one `_PerRecordingStream` per composite channel — a lone
composite channel is just the N=1 case, so every existing single-recording behavior is
unchanged. `_stream()` reads one chunk from every still-active stream each iteration (an
exhausted stream contributes silence while others continue — no looping, matching the
original single-recording behavior), applies that stream's own gain and (if present)
coherent DSP independently, then sums all contributions into the one signal actually
sent to the device. `CompositeChannel.gain_offset_db` — an existing field, never
consumed anywhere before this — is finally read here: linear scale `10**(gain_offset_db
/ 20)` applied per stream before summation, so an author can balance relative loudness
between recordings sharing a channel. No output-level clipping/backoff policy is
modeled beyond that (matches `StreamingSDRAdapter`'s pre-existing "no gain policy...
flagged as a follow-up" note). Every recording mixed onto one channel must share a
sample rate; a mismatch is rejected at `preflight` with a clear error — no resampling is
attempted.

## Consequences

- Fully additive and backward-compatible: an `L0_SIMULATED` plan's `start_run` path,
  every existing `SDRAdapter` call site, and every single-recording-per-channel scenario
  behave exactly as they did before this ADR — verified by running the full pre-existing
  test suite unchanged alongside the new tests.
- L1 is the execution ceiling this system can honestly claim today. L2/L3/L4 remain
  declarable (for a scenario or a future Agent capability to grow into) but L2 executes
  identically to L1, and L3/L4 only ever produce a compile-time warning, never a false
  claim of hardware capability.
- Doppler continuity is coherent-group-only; a MONITOR receiver watching a moving
  transmitter sees no Doppler modeling in this slice (a real, documented gap — extending
  it would need a new receiver-to-link association this ADR does not introduce).
- Delay remains piecewise-constant; only Doppler-driven phase is continuous.
- `FractionalDelayLine`'s linear interpolation and the ~1s Doppler-sampling cadence are
  both documented simplifications, not claims of measurement-grade fidelity — this slice
  proves the mechanism (a phase-continuous NCO driven by a real, computed schedule), not
  a production-grade resampler.
- Real-hardware verification (AIR7311/X440) of the DSP pipeline is explicitly out of
  scope here and does not block this work — tracked as a future, optional pass matching
  M9/M10's precedent, not attempted or claimed in this ADR.
