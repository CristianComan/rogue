# SigMF Drone Replay Tool

Backup solution for replaying recorded drone RF signals (SigMF) locally on
AIR-T 7311, AIR-T 7201 and Ettus USRP X440. Simple, manual, file-based, no
network dependency. Used for exercise signal injection into **conducted or
shielded** test setups.

## Safety rules (non-negotiable)

1. `play` is a **dry run by default**. Real transmit requires `--arm`.
2. Every scenario declares `max_tx_gain_db`. The backend must refuse any gain
   above it. No hidden default for this field.
3. Before any real transmit, print: "Conducted or shielded setup only.
   Radiated emission requires spectrum/range authorisation." and require the
   operator to type `yes`.
4. Tests and CI must never open a real radio. Backends are tested with mocks;
   hardware imports (`SoapySDR`, `uhd`) are lazy and live only in `backends/`.
5. Never auto-arm, never add a flag that skips the confirmation prompt.

## Pipeline

```
catalog (SigMF files) + scenario (YAML)
   -> validate -> resolve (geometry -> recording)
   -> compile (shift, resample, place, sum) -> composite SigMF + report
   -> play (backend per radio)
```

Replay is always of a **compiled composite file**, so the radio streams one
file and all timing/mixing logic lives in the compiler.

## Data model

- Recordings: one SigMF per drone per variant. 15 drones x 3 variants:
  - `drone`      = drone-side emission only (downlink / video / telemetry)
  - `controller` = controller-side emission only (uplink / RC)
  - `both`       = both emitters present
- Catalog: `catalog/drones.yaml`, a top-level mapping `drone -> variants ->
  {drone|controller|both: {meta: path}}`. The scanner fills in datatype,
  sample rate, centre frequency, duration from the `.sigmf-meta`
  (`global.core:datatype`, `global.core:sample_rate`,
  `captures[0].core:frequency`). Missing variants are warnings, not errors.
- Scenario: `scenarios/*.yaml`, see `src/schema.py` (source of truth).

## Geometry rule (variant selection)

Distance is NOT an attenuation. Each event states which emitters the observer
is near, and the tool replays the recording as captured:

| near              | recording  |
|-------------------|------------|
| [drone]           | drone      |
| [controller]      | controller |
| [drone, controller] | both     |
| []                | none, event is a no-op (warn) |

`use: <variant>` on an event overrides the rule (warn if `near` is also set).
Rule table lives in `schema.RULE_TABLE`; do not duplicate it elsewhere.

## Compile semantics

For each resolved, non-skipped event:
1. Read samples via memmap; convert to cf32 internally (support cf32_le,
   ci16_le, ci8, cu8 at minimum; error clearly on others).
2. Frequency-shift by `(rec_centre - radio_centre)`.
3. Resample (polyphase) from recording rate to `radio.rate_msps`.
4. Cut/loop to `dur_s`. If the recording is shorter and `loop: false`,
   truncate and warn. If looping, warn about the seam discontinuity
   (hopping/burst signals).
5. Apply `gain_db` (level balancing only, default 0).
6. Place at `start_s` and sum into the composite.

Then: apply `noise_policy` (`keep` = leave recorded noise floor, `trim_bursts`
= gate to active bursts), normalise to `headroom_dbfs` peak, **log the scale
factor**, write composite cf32 SigMF + `report.json` + spectrum PNG.

Report must list per event: drone, variant chosen, reason (e.g. "near drone
only -> drone"), start/end, loop, and overlap warnings (same time AND
overlapping frequency span).

### Fit and size checks (hard errors)

- Each recording's span (centre +/- sample_rate/2, conservative) after
  shifting must fit inside the radio's usable bandwidth.
- Radio centre must be within the radio's frequency range.
- `rate_msps` and bandwidth must not exceed radio limits (`RADIO_LIMITS`).
- Composite size = duration x rate x 8 bytes (cf32). At 100 MSPS that is
  800 MB/s, so 60 s is about 48 GB. Refuse (or require `--allow-large`) if it
  exceeds the disk budget, and warn if it exceeds the RAM budget. Prefer
  lower rates (e.g. 25-30 MSPS) when the signals are narrowband.

## Backends (`src/backends/`)

Common interface: `play(composite_meta, gain_db, repeat, arm)`.

- `airt.py` (7311 and 7201, identical flow): SoapySDR, `driver=SoapyAIRT`.
  Based on Deepwave's "Transmit with Python" tutorial. Set TX rate, centre
  frequency and gain, `setupStream(SOAPY_SDR_TX, ...)`, `writeStream` loop.
  TX accepts numpy arrays/lists only (not cupy). Convert cf32 -> CS16 for the
  wire to halve bandwidth. If the composite exceeds the RAM budget, stream
  from a memmap with a prefetch thread; otherwise preload into RAM.
  7311 has two AD9371 (4 channels); channel indexing must be verified on
  hardware.
- `x440.py` (UHD 4.5+): Prefer the RFNoC Replay block (gap-free from DRAM) via the
  UHD Python API; fall back to shelling out to the UHD
  `rfnoc_replay_samples_from_file` / `tx_samples_from_file` examples. Verify
  flags with `--help` on the installed UHD version.

Radio limits (from Deepwave and Ettus docs, see `schema.RADIO_LIMITS`):
- AIR-T 7311/7201: 300 MHz-6 GHz, 100 MHz BW, 125 MSPS max, +20 dBm max.
- X440: 30 MHz-4 GHz only (direct sampling; tunable down to 1 MHz). **No
  5.8 GHz without an external upconverter**, so 5.8 GHz signals (e.g. FPV
  video, OcuSync 5.8) must go through an AIR-T. IBW is 1.6 GHz on 2 channels
  but 400 MHz on 8 channels, depending on the FPGA image; limits default to
  the conservative 400 MHz. Max output about 0 dBm. Needs UHD 4.5 or later.
- Validator must give a clear error when a recording's band is outside the
  chosen radio's range (e.g. "recording at 5.8 GHz cannot be replayed on
  x440; use airt7311").

## CLI

```
replay scan <rec_dir> -o catalog/drones.yaml
replay validate <scenario.yaml> --catalog catalog/drones.yaml
replay compile  <scenario.yaml> --catalog ... -o out/<name>/
replay play     <out/name/composite.sigmf-meta> --radio airt7311 [--arm]
```

## Conventions

- Python 3.10+, pydantic v2, PyYAML, numpy, scipy, `sigmf` package.
- Keep modules small and typed. No network calls. No global state.
- pytest. Use synthetic SigMF files (tones/noise) in tests; no real recordings
  in the repo.
- Every validation problem is an `Issue(level, where, message)`; `validate`
  prints all of them and exits non-zero only on errors.

## Build order and status

- [ ] 1. `schema.py` (provided, review and extend), catalog scanner
- [ ] 2. Validator (datatype, rate, bandwidth fit, timeline overlap, gain cap)
- [ ] 3. Tests with synthetic SigMF
- [ ] 4. Compiler + report
- [ ] 5. AIR-T backend (bring up conducted, with spectrum analyser)
- [ ] 6. X440 backend
- [ ] 7. CLI polish, README with an operator checklist

## Open questions (ask the user, do not guess)

- Gain units/ranges per radio (calibrate conducted, then set caps).
- Default noise policy after seeing real recordings.
- Whether some recordings are non-contiguous or already hopping-limited.
