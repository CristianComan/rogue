# Playing a scenario for real, with multiple drones

A deep dive on top of the README's operator checklist: how a scenario's
`events` list actually works, how several drones end up in one
transmission, and the real-hardware gotchas already found running this
against an AIR7311. See `README.md` for install/deploy and the 4-channel
direct-loopback workflow; this doc is about the **content** of a
scenario and taking it to real TX.

## 1. The model, precisely

One scenario compiles to **one composite SigMF file**, played out **one
radio configuration** (one center frequency, one sample rate, one TX
gain). Every drone in the scenario is a separate **event** placed on
that same timeline and, if two events overlap in time, summed into the
same samples — there's no per-drone sub-channel inside one composite.
If you want different drones transmitting from genuinely different
channels at once, that's several *scenarios* (see §6).

```yaml
name: my_scenario                 # [A-Za-z0-9_-]+, also the out/<name>/ dir
description: ""                   # free text, optional

radio:
  type: airt7311                  # airt7311 | airt7201 | x440 (x440 play not implemented yet)
  channel: 0
  center_mhz: 2450                # shared by every event -- see §4
  rate_msps: 125                  # shared by every event -- see §5 (native-rate lesson)
  tx_gain_db: -10
  max_tx_gain_db: -5               # mandatory; tx_gain_db > this is rejected at parse time
  device_args: "driver=SoapyAIRT"  # omit to fall back to ROGUE_AIR7311_DEVICE_ARGS-style env

events:                            # one or more -- this is "multiple drones"
  - drone: "02"
    near: [drone]
    start_s: 0.0
    dur_s: 5.0
    loop: true
    gain_db: 0.0

noise_policy: keep                 # keep | trim_bursts
headroom_dbfs: -3.0                # composite peak target, <= 0
```

## 2. One event = one drone's emission, placed in time

| Field | Meaning |
|---|---|
| `drone` | key into the catalog (`replay scan`'s output), e.g. `"02"` |
| `near` | which emitter(s) an observer is near — drives variant selection, §3 |
| `use` | explicit variant override (`drone`/`controller`/`both`), skips the `near` rule |
| `start_s` / `dur_s` | where this event sits on the composite's timeline |
| `loop` | if the recording is shorter than `dur_s`: tile it (seam discontinuity, logged as a warning) vs. leave the remainder silent |
| `gain_db` | software level-balancing for *this* event only, applied before summing |

`near: []` and no `use` is a legal no-op ("nothing visible", a `warning`,
not an `error` — useful for sketching out a scenario's timeline before
every drone has a catalog entry).

## 3. Geometry -> variant (the `near` rule)

Distance isn't modelled as attenuation — each event says which
emitter(s) an observer is near, and the matching recording plays back
*as captured*:

| `near` | variant used |
|---|---|
| `[drone]` | `drone` (drone-side emission only) |
| `[controller]` | `controller` (controller-side emission only) |
| `[drone, controller]` | `both` |
| `[]` | none — event skipped (warning) |

`use: both` (etc.) skips this table entirely — set it when you want a
specific variant regardless of geometry. The real drone corpus (see
README's "Reusing ROGUE's own recordings") only has `drone` and `both`
recordings for a handful of drones, no standalone `controller` — `replay
scan --layout rogue-corpus` already tells you this per-drone via
"missing 'controller' variant" warnings; `replay validate` will error if
an event resolves to a variant that drone doesn't actually have.

## 4. Multiple drones must share a reachable band

**`radio.center_mhz`/`rate_msps` are one shared value for the whole
scenario** — every event's recording gets frequency-shifted from its own
captured center to `radio.center_mhz` and resampled to `radio.rate_msps`
before being summed in. That only makes physical sense if every event's
recording is reasonably close to that one center.

The real drone corpus mixes bands: `drone`/`los`/`nlos`-variant
recordings are all captured at 2450 MHz, `both`-variant recordings at
5800 MHz. Mixing a 2450 MHz drone event with a 5800 MHz `both` event in
*one* scenario means one of them is ~3.35 GHz away from wherever you set
`center_mhz` — `validate`/`compile` reject that outright:

```
error: events[1] (04): recording centre is +3350.000 MHz from the radio's
tuned centre, outside its +/-50.000 MHz usable range
```

This is a hard error (CLAUDE.md's "recording span ... must fit inside
the radio's usable bandwidth", tightened after real-hardware testing —
see §5): no sample-rate choice moves where a recording's energy actually
sits. Keep all of one scenario's events within one band; use a separate
scenario (and separate `compile`/`play`, possibly a different channel)
for a different band.

You'll also see a **non-blocking** warning like:

```
warning: events[0] (02): recording's conservative span -62.500..62.500 MHz
(assumes the full sample rate is occupied) exceeds the radio's
+/-50.000 MHz usable bandwidth -- fine if the actual signal content is
narrower than that
```

That one's fine to proceed past — it's a deliberately pessimistic check
(assumes the recording's *entire* sample rate is occupied signal, which
a 125 Msps capture of a narrowband drone link never actually is).

## 5. Picking `rate_msps`: use the recording's native rate

Confirmed against real AIR7311 hardware: SoapyAIRT's TX `setSampleRate()`
only works at whatever the device's master clock rate is currently set
to, and the AIR-T only supports a handful of fixed master-clock/IF
frequencies. `replay play` sets the master clock to match `rate_msps`
automatically — **but if you pick an arbitrary `rate_msps` that isn't one
of those fixed frequencies, you've silently put the device in a
non-standard clock state for no benefit.**

The drone corpus is captured at 125 Msps. Use `rate_msps: 125` — it
matches the recordings exactly (no resampling needed) and is a rate
already confirmed to work. Don't derive `rate_msps` from
`RADIO_LIMITS.max_bw_mhz` (100 MHz for the AIR7311) — that number is the
TX chain's **analog filter passband**, a separate, fixed hardware
characteristic, not a sample-rate recommendation (§4's warning is where
that number actually matters).

## 6. Sequential vs. simultaneous drones

**Sequential** (one drone at a time, composite timeline divided into
slots) — the common case, and the only one that avoids the overlap
warning:

```yaml
events:
  - drone: "02"
    near: [drone]
    start_s: 0.0
    dur_s: 0.1
    loop: true
  - drone: "03"
    near: [drone]
    start_s: 0.1
    dur_s: 0.1
    loop: true
  - drone: "06"
    near: [drone]
    start_s: 0.2
    dur_s: 0.1
    loop: true
```

**Simultaneous** (two drones' signals summed together, e.g. to test a
receiver's ability to separate two emitters) — give two events
overlapping `start_s`/`dur_s` windows. `validate` flags this with a
`warning`, not an `error` — intentional overlap is legal, you're just
told about it:

```yaml
  - drone: "07"
    near: [drone]
    start_s: 0.3
    dur_s: 0.1
  - drone: "08"
    near: [drone]
    start_s: 0.3
    dur_s: 0.1
```

```
warning: events[3] & events[4]: overlap in time and in frequency span
```

Both land in the same composite, same frequency region (both are
2450 MHz drone-only recordings, same `center_mhz`) — their samples get
summed, so a receiver sees both at once. Use different `gain_db` per
event if one should be louder than the other.

## 7. Composite size at 125 Msps — keep `dur_s` short

`cf32_le` is 8 bytes/sample, so at the corpus's native 125 Msps a
composite costs **1 GB per second of `duration_s`**, uncompressed, before
`compile`'s own disk-budget check (default 100 GB) even comes into play.
A naive "5 seconds per drone x 5 drones" scenario is a 125 GB composite —
likely to exhaust RAM/disk on a real AIR-T (an embedded Jetson module,
not a workstation) long before you get to `play`.

Keep each event's `dur_s` short (tenths of a second is plenty to show up
clearly in a spectrogram or on a spectrum analyzer) and reach for
`--repeat` at **play** time (§8) for a sustained, multi-second
on-air transmission instead of a long `dur_s`/many `loop: true`
iterations baked into the composite itself.

## 8. Full worked example: 5 drones, sequential + simultaneous

```yaml
# scenarios/multi_drone.yaml
name: multi_drone
description: "Five drones, 2450 MHz: three sequential, two simultaneous."
radio:
  type: airt7311
  channel: 0
  center_mhz: 2450
  rate_msps: 125
  tx_gain_db: -10
  max_tx_gain_db: -5
  device_args: "driver=SoapyAIRT"
events:
  - drone: "02"
    near: [drone]
    start_s: 0.0
    dur_s: 0.1
    loop: true
  - drone: "03"
    near: [drone]
    start_s: 0.1
    dur_s: 0.1
    loop: true
  - drone: "06"
    near: [drone]
    start_s: 0.2
    dur_s: 0.1
    loop: true
  - drone: "07"
    near: [drone]
    start_s: 0.3
    dur_s: 0.1
    loop: true
  - drone: "08"
    near: [drone]
    start_s: 0.3
    dur_s: 0.1
    loop: true
    gain_db: -6.0        # a bit quieter than drone 07 in the same window
noise_policy: keep
headroom_dbfs: -3.0
```

That's 0.4 seconds total (`duration_s = max(event.end_s)`), drones
02/03/06 each getting a clean 0.1 s slot and 07+08 transmitting together
for the last 0.1 s — confirmed end to end (`validate`, `compile`,
`report.json`'s per-event `start_s`/`end_s`, and `spectrum.png` showing
five visually distinct segments) against the real corpus. At 125 Msps
that's a ~380 MB composite, compiling in well under a minute.

```bash
# 1. Catalog (once; re-run after adding/removing recordings)
.venv/bin/replay scan ~/Documents/drone-corpus -o catalog/drones.yaml --layout rogue-corpus

# 2. Validate -- read every line, especially any `error`
.venv/bin/replay validate scenarios/multi_drone.yaml --catalog catalog/drones.yaml

# 3. Compile -- composite + report.json + spectrum.png + radio.json
.venv/bin/replay compile scenarios/multi_drone.yaml --catalog catalog/drones.yaml -o out/
```

Expect exactly one `warning` about time+frequency overlap, for the two
intentionally-simultaneous events (`events[3] & events[4]`) — not for
the back-to-back ones (`02`->`03`->`06`->`07`): adjacent, non-overlapping
`start_s`/`dur_s` windows are never flagged, even though float addition
(`0.2 + 0.1 != 0.3` in binary floating point) would otherwise make
"back-to-back" and "overlapping by a fraction of a microsecond" look the
same — `validate_scenario` tolerates exactly that, see
`src/replay_cli/validate.py::_TIME_EPSILON_S`.

**Before transmitting anything**, actually look at what `compile` wrote:

```bash
cat out/multi_drone/report.json     # per-event drone/variant/reason/start/end, overlap warnings
```

`out/multi_drone/spectrum.png` is a real spectrogram of the composite —
confirm it has five visually distinct segments matching the scenario
before you key a real transmitter.

## 9. Playing it for real

Dry run first — always, even if you've done this before:

```bash
.venv/bin/replay play out/multi_drone/composite.sigmf-meta --radio airt7311
```

Then, with your TX safely terminated (dummy load, attenuator into a
spectrum analyzer, or a real antenna only if you hold the appropriate
authorization — CLAUDE.md safety rule 3):

```bash
.venv/bin/replay play out/multi_drone/composite.sigmf-meta --radio airt7311 --arm
```

You'll see the exact plan line (device, channel, frequency, rate, gain,
duration) printed before anything happens, then the safety banner, then
a typed `yes` prompt — there is no flag that skips this (CLAUDE.md
safety rule 5). The whole 20-second composite plays once and stops. Use
`--repeat N` to play the whole scenario `N` times back-to-back instead of
authoring a longer `dur_s`/more `loop: true` padding by hand:

```bash
.venv/bin/replay play out/multi_drone/composite.sigmf-meta --radio airt7311 --arm --repeat 3
```

Ctrl+C at any point still closes the TX stream cleanly (CLAUDE.md rule
"Emergency stop paths receive dedicated tests" — the same discipline
applies here even without a formal e-stop command).

## 10. Transmitting the same content on several channels at once

That's a different thing from "multiple drones" (§6-7's events are one
composite, one channel) — see README's "Direct TX->RX cable loopback"
section for `--channels`/`--tx-attenuation-db`, which plays *the same*
composite on several TX channels simultaneously. The two compose: build
a multi-drone composite exactly as above, then play it on channel 0
only (`replay play ... --arm`, no `--channels`) or on several channels
at once (`replay play ... --channels 0,1,2,3 --tx-attenuation-db 20
--arm`) if that's genuinely what you want all four channels to transmit.

## 11. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `Requested sample rate of N MHz not supported by current master clock rate!` | `rate_msps` isn't a rate the AIR-T's master clock actually supports | Use the recordings' native rate (`rate_msps: 125` for the drone corpus) — see §5 |
| `recording centre is +N MHz from the radio's tuned centre, outside its usable range` | an event's recording is on a different band than `radio.center_mhz` | Keep every event in one scenario on the same band (§4); split into separate scenarios otherwise |
| `recording's conservative span ... exceeds the radio's usable bandwidth` (warning) | pessimistic full-sample-rate assumption vs. the TX filter's passband | Informational only — check `spectrum.png`, proceed if the real content is narrower |
| `drone 'X' has no 'Y' recording` | the event's resolved variant isn't in the catalog for that drone | Check `replay scan`'s "missing variant" warnings; pick a drone/variant that exists, or `use:` a different variant |
| `tx_gain_db N exceeds max_tx_gain_db M` | `RadioSpec`'s mandatory safety cap (CLAUDE.md rule 2) | Lower `tx_gain_db` or deliberately raise `max_tx_gain_db` — never silently bypassed |
| `overlap in time and in frequency span` (warning) | two events' windows overlap on the same band | Expected if you intended simultaneous drones (§6); separate `start_s`/`dur_s` otherwise |
