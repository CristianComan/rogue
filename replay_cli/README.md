# SigMF Drone Replay Tool

Backup solution for replaying recorded drone RF signals (SigMF) locally on
AIR-T 7311, AIR-T 7201 and Ettus USRP X440. See `CLAUDE.md` for the full
design, safety rules and pipeline. Independent of the main ROGUE
`rogue`/`agents` packages — its own dependencies, its own venv.

X440 playback is not yet implemented (`backends/x440.py` is a stub) —
AIR-T 7311/7201 are the current priority.

**Building a scenario with several drones, and taking it to a real
transmit?** See `docs/playing-scenarios.md` — this README's operator
checklist (§below) covers the single-event mechanics; that doc covers
the `events` list, geometry-driven variant selection, sequential vs.
simultaneous drones, and real-hardware lessons learned (rate_msps,
band-matching).

## Install (local development / control host)

```bash
cd replay_cli
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

This is enough to `scan`/`validate`/`compile` and to `play` in dry-run
(no `--arm`) anywhere — those never touch a real radio. Actually
transmitting needs the steps below, run **on the radio's own host**.

## Deploying to an AIR-T 7311 / AIR-T 7201 host (bare metal, local)

Each AIR-T is driven locally by a process running on that unit's own
embedded Linux host (it's a SoapySDR-native SDR+compute board, not a
networked one) — there is no remote/network mode for this backend.
`air-t-host` below is a placeholder for `user@<the unit's LAN IP>`
(e.g. this lab's current AIR-T 7311 is `airt@10.42.0.206`); both
`replay_cli/` and the recordings corpus live under `~/Documents/` on
that host.

**If this AIR-T has internet access**, steps 1-2 below work as shown.
**If it's air-gapped (no internet), skip to "Offline install" below
instead** — it covers getting every package (this tool's own
dependencies and SoapySDR's system bindings) onto a host with no
network access at all.

1. Copy this `replay_cli/` directory onto the AIR-T (it's independent of
   the rest of the ROGUE repo — nothing else is needed):

   ```bash
   rsync -av --exclude .venv --exclude out --exclude .pytest_cache \
     replay_cli/ air-t-host:~/Documents/replay_cli/
   ```

2. On the AIR-T itself, install the same way as local development:

   ```bash
   ssh air-t-host
   cd ~/Documents/replay_cli
   python3 -m venv .venv
   .venv/bin/pip install -e ".[dev]"
   ```

3. SoapySDR's Python bindings are **not** part of this `pip install`
   (there is no reliable PyPI package for them — same constraint ROGUE's
   own `docs/architecture/deployment.md` §7 and ADR-010 already record
   for the main repo's `DeepwaveAIR7311Adapter`). Confirm they're present
   on the AIR-T's system Python and importable from this venv:

   ```bash
   SoapySDRUtil --find                                    # confirm `driver = SoapyAIRT`
   .venv/bin/python -c "import SoapySDR; print(SoapySDR.__file__)"
   ```

   If the venv's Python can't see them, either build/install SoapySDR's
   bindings against this venv's interpreter, or create the venv with
   `--system-site-packages` so it inherits the AIR-T's own system
   SoapySDR install. (If this AIR-T unit's bindings are only built for
   an older Python than this venv's, per ADR-011's note on the lab
   AIR7311 — SoapyRemote is the same documented workaround ROGUE's main
   adapter used; not reimplemented here, same caveat applies.)

4. Run the operator checklist below, from this host, with `--arm` only
   once cabled into a conducted/shielded test setup.

The AIR-T 7201 is driven identically — same steps, same backend, just a
different `driver=` string for its own SoapySDR identity (confirm with
`SoapySDRUtil --find` on that unit).

## Deploying to an X440 host (bare metal, local)

X440 playback (`backends/x440.py`) isn't implemented yet, so there's
nothing to transmit with here today — but `scan`/`validate`/`compile`
and a dry-run `play --radio x440` all work already, so the same install
can be used to stage/validate scenarios from the X440 host ahead of that
backend landing. If this host has no internet either, use "Offline
install" below the same way as for an AIR-T host (just without the
SoapySDR steps — no UHD install is needed yet, since `backends/x440.py`
doesn't import `uhd` at all until it's actually implemented, checklist
item 6 in `CLAUDE.md`):

```bash
rsync -av --exclude .venv --exclude out --exclude .pytest_cache \
  replay_cli/ x440-host:~/replay_cli/
ssh x440-host
cd ~/replay_cli
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

## Offline install (no internet on the radio host)

Both the AIR-T and X440 hosts in this lab are commonly on an isolated
network with no outbound internet. `pip` can't reach PyPI from there, so
every package has to be fetched elsewhere and carried over.

### 1. This tool's own Python dependencies

On **any machine with internet access**, download every wheel/sdist
`replay_cli` needs (`pip` resolves the full dependency tree, not just
the top-level ones) into a local folder:

```bash
cd replay_cli
pip download -d offline_packages ".[dev]"
```

**Architecture matters.** An AIR-T is an aarch64 Jetson/Orin module
running Python 3.10 (its `airstack` image — see ADR-011); if you run the
command above on a regular x86_64 laptop, `numpy`/`scipy`/`matplotlib`
need prebuilt **aarch64** wheels, which may or may not exist for every
version on PyPI. Pick one:

- **Simplest and most reliable**: run `pip download` on a machine that's
  already aarch64 + Python 3.10 — e.g. the AIR-T itself, the one time
  it's ever plugged into a network with internet (even briefly, before
  it's moved to the isolated lab network), or another Jetson/AIR-T unit.
  This guarantees every wheel actually matches.
- **From a non-matching machine** (e.g. your x86_64 dev laptop), force
  pip to fetch aarch64/cp310 wheels explicitly — this only works if
  PyPI actually has them for every dependency, so check the output
  carefully for anything that falls back to a source (`.tar.gz`) package,
  since that needs a matching compiler toolchain to build and won't just
  work by copying it over:

  ```bash
  pip download -d offline_packages ".[dev]" \
    --platform manylinux2014_aarch64 --platform manylinux_2_17_aarch64 \
    --python-version 310 --implementation cp --abi cp310 \
    --only-binary=:all:
  ```

  (For an X440 host this is usually unnecessary — those are typically
  ordinary x86_64 Linux PCs, so `pip download -d offline_packages
  ".[dev]"` run on any similar x86_64/Python 3.x machine is enough.)

Copy `replay_cli/` and the `offline_packages/` folder over together
(USB drive, or a direct cable/LAN if the lab network has no internet
egress but still routes between hosts):

```bash
rsync -av --exclude .venv --exclude out --exclude .pytest_cache \
  replay_cli/ air-t-host:~/Documents/replay_cli/
rsync -av offline_packages/ air-t-host:~/Documents/replay_cli/offline_packages/
```

Then, **on the air-gapped host itself**, install with no network access
at all — `--no-index` refuses to reach out to PyPI, `--find-links` points
`pip` at the folder you copied over instead:

```bash
ssh air-t-host
cd ~/Documents/replay_cli
python3 -m venv .venv
.venv/bin/pip install --no-index --find-links=offline_packages -e ".[dev]"
```

### 2. SoapySDR's system bindings (AIR-T only, apt, not pip)

Same offline problem, different package manager. On a machine running
the **same OS/image** as the AIR-T (ideally the AIR-T itself, briefly
connected, same as above) — first confirm the real package name for
your image, since it isn't fixed across Deepwave `airstack` releases:

```bash
apt-cache search soapysdr
```

Then download (not install) those packages plus their own dependencies:

```bash
apt-get install --download-only -y <the package name(s) you found>
cp /var/cache/apt/archives/*.deb ~/soapysdr_debs/
```

Copy `soapysdr_debs/` to the air-gapped AIR-T and install from the
local files, no network needed:

```bash
rsync -av soapysdr_debs/ air-t-host:~/soapysdr_debs/
ssh air-t-host
sudo dpkg -i ~/soapysdr_debs/*.deb
```

If this exact AIR-T was already provisioned with SoapySDR by Deepwave
before it went on the isolated network, check first with `dpkg -l | grep
-i soapy` — it may already be there and none of this section is needed.

## Reusing ROGUE's own recordings

The main ROGUE repo already has a local drone-RF corpus at
`../recordings/drone-corpus/15June2022/` (one subdirectory per drone_id,
`no_drone` as the ambient baseline) — the same source
`scripts/ingest_drone_corpus.py` reads before uploading to the main
repo's own M4 catalogue/MinIO. **This directory is git-ignored and local
to this machine** (CLAUDE.md's root `.gitignore`, and the main repo's own
CLAUDE.md rule against committing large captures) — it does not travel
with `git clone`/`git pull`, so copy it to each radio host the same way
as `replay_cli/` itself, e.g.:

```bash
rsync -av ../recordings/drone-corpus/15June2022/ air-t-host:~/Documents/drone-corpus/
```

Scan it with `--layout rogue-corpus` instead of the default simple
layout — variant is read from each recording's own `experiment:scenario`
SigMF field (`air`/`los`/`nlos` -> `drone`, `both` -> `both`; this
campaign has no `controller`-only recordings, so expect a "missing
'controller' variant" warning for every drone — that's accurate, not a
bug):

```bash
.venv/bin/replay scan ~/Documents/drone-corpus -o catalog/drones.yaml --layout rogue-corpus
```

**Rate/bandwidth note:** this corpus was captured at 125 Msps — use
`radio.rate_msps: 125` for a scenario built from it, matching the
AIR7311's master clock as it already is. **Don't pick an arbitrary
`rate_msps`** (e.g. 100, to try to satisfy the bandwidth check below):
confirmed against real hardware, SoapyAIRT's TX `setSampleRate()` only
works at whatever the device's master clock rate is currently set to,
and the AIR-T only supports a handful of fixed master-clock/IF
frequencies — 100 MHz isn't one of them, and `replay play` silently
reconfigures the master clock to match whatever `rate_msps` you asked
for, which is disruptive if it isn't actually a valid rate for this
hardware. 125 Msps is the one already confirmed to work.

The AIR7311's `RADIO_LIMITS.max_bw_mhz = 100 MHz` is a *separate* thing:
the TX chain's analog filter passband, a fixed hardware characteristic —
it does not mean "pick a sample rate at or below 100." `validate`/
`compile` use it as a conservative (worst-case, full-sample-rate)
bandwidth-fit check: a 125 Msps recording's own centre frequency must
still be reachable (hard **error** otherwise — no sample rate fixes a
wrong centre), but the full ±62.5 MHz conservative span exceeding the
filter's ±50 MHz is only a **warning** — real drone RF content is
normally much narrower than the full capture rate, so it likely still
passes through the filter fine even though the pessimistic estimate
doesn't fit. `report.json` always lists it; check it, don't just ignore
every warning blindly.

## Operator checklist

For a single-drone scenario, this is everything you need. For several
drones in one scenario (or one scenario replayed for real), see
`docs/playing-scenarios.md`.

1. **Scan** your recordings into a catalog — the simple one-subdirectory-
   per-variant layout, or `--layout rogue-corpus` for ROGUE's own corpus
   (see above):

   ```bash
   .venv/bin/replay scan /path/to/recordings -o catalog/drones.yaml
   ```

2. **Validate** your scenario against that catalog — fix every `error`;
   `warning`s are advisory:

   ```bash
   .venv/bin/replay validate scenarios/my_scenario.yaml --catalog catalog/drones.yaml
   ```

3. **Compile** — produces `out/<name>/composite.sigmf-meta` (+ `.sigmf-data`),
   `report.json`, `spectrum.png`, `radio.json`:

   ```bash
   .venv/bin/replay compile scenarios/my_scenario.yaml --catalog catalog/drones.yaml -o out/
   ```

   Read the report before transmitting anything — check the per-event
   variant/reason list and any overlap warnings.

4. **Play — dry run first** (default; no radio is opened):

   ```bash
   .venv/bin/replay play out/my_scenario/composite.sigmf-meta --radio airt7311
   ```

5. **Play — real transmit**, conducted/shielded setup only:

   ```bash
   .venv/bin/replay play out/my_scenario/composite.sigmf-meta --radio airt7311 --arm
   ```

   You'll be shown the safety banner and must type `yes` to proceed. There
   is no flag to skip this confirmation (by design — see `CLAUDE.md`
   safety rule 5).

## Direct TX->RX cable loopback (all 4 channels at once)

To check every TX->RX pair is alive (TX0->RX0, TX1->RX1, TX2->RX2,
TX3->RX3 cabled directly), just replay a real scenario on all 4 TX
channels at once and watch all 4 RX channels for it arriving — no
separate loopback-specific tool needed, the normal `compile`/`play`
pipeline above already does this with two additions: `play --channels`
to transmit on several channels simultaneously, and a monitoring script
that watches the RX side.

**A direct cable has ~0 dB path loss** — unlike over-the-air use, there's
no free-space attenuation between TX and RX, so even modest TX gain can
saturate or damage the RX front end. `--tx-attenuation-db` adds extra
*software* headroom on top of the scenario's own `tx_gain_db` (scales the
samples down before they reach the device) specifically for this —
independent of, and in addition to, any hardware inline attenuator you
may also have fitted. Start high (e.g. 20-30 dB) and reduce only if the
monitor shows nothing.

1. Compile a scenario as usual (steps 1-3 above; a single-channel
   scenario is fine — the same composite gets played on every TX channel
   listed below).

2. In one terminal, start the RX monitor — it writes `waterfall.png`
   (refreshed every second by default), one panel per RX channel:

   ```bash
   .venv/bin/python scripts/rx_monitor.py --device-args "driver=SoapyAIRT" \
       --channels 0,1,2,3 --center-freq-hz 2450000000 --out waterfall.png
   ```

   Pull `waterfall.png` over (e.g. `scp airt-host:~/Documents/replay_cli/waterfall.png .`)
   to view it — the AIR-T is normally headless/SSH-only, so this never
   opens an interactive plot window.

3. In another terminal, play the compiled composite on all 4 TX channels
   at once, with extra software attenuation for the direct connection:

   ```bash
   .venv/bin/replay play out/my_scenario/composite.sigmf-meta \
       --channels 0,1,2,3 --tx-attenuation-db 20 --arm
   ```

   Same safety banner and typed `yes` confirmation as a normal `play
   --arm` — asked once for all 4 channels, not once each.

4. Watch `waterfall.png` update — each RX*N* panel should show the
   transmitted signal appear once step 3 starts. A channel whose panel
   stays empty, or whose content doesn't match what's expected, points at
   that specific TX/RX pair (bad cable, wrong channel mapping, dead
   front end) rather than the setup as a whole.

Stop the monitor with Ctrl+C (or `--duration-s N` to stop it
automatically); it always closes its RX streams on exit.
