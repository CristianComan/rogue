# ADR-019: Manual Replay CLI (M19)

**Status:** Accepted — ready for real-hardware bring-up; not itself hardware-verified

**Not the same tool as `replay_cli/`:** a second, independent CLI
(`replay_cli/`, its own `CLAUDE.md`/`pyproject.toml`/venv, no dependency
on `rogue`/`agents`) was added afterward for the same AIR-T 7311/7201/
X440 hardware, built around compiling a multi-drone scenario + catalog
into one composite SigMF file rather than streaming a recording straight
through ROGUE's real adapters. The two don't conflict — `rogue-manual-
replay` (this ADR) is the ROGUE-integrated single-channel bring-up tool;
`replay_cli/replay` is the standalone, scenario/catalog-driven one. See
`replay_cli/CLAUDE.md` and `docs/architecture/implementation-plan.md`'s
supplemental row for it.

## Context

M9/M10 delivered real `EttusX440Adapter`/`DeepwaveAIR7311Adapter` code but
left both hardware-unverified — this dev environment has neither device.
The user now has real hardware for the first time (an X440 and three
SoapySDR-native Deepwave AIR-T units — AIR7311, AIR7201, AIR8201 — cabled
over RF loopback) and wants to start bring-up before tackling full HIL
integration into the scenario/orchestration stack (M20+).

The only existing way to key a real channel is the full path: Postgres +
MinIO + NATS + FastAPI backend + a distributed `AgentRuntime` process
(`agents/common/main.py`) + a compiled `ReplayPlan` from a real scenario.
That's correct for M20+, but it's the wrong tool for "is this channel even
keying over loopback" — there was no lightweight, config-driven way to
drive one physical channel by hand, without the control plane, matching
what CLAUDE.md §13 calls out as the step between "real SDR adapters" and
"synchronized multi-SDR replay."

## Decision

### A standalone CLI, not a backend feature

`agents/cli/manual_replay.py` (+ `agents/cli/config.py`) is a new,
backend-free package: no Postgres, no MinIO, no NATS, no scenario. It
builds a real `EttusX440Adapter`/`DeepwaveAIR7311Adapter` directly and
drives one `(device_id, channel_index)` through the exact same
`SDRAdapter` protocol (`reserve → preflight → configure → arm → start →
stop`, plus `status`/`emergency_stop`/`discover`) the real distributed
Agent uses — bring-up done with this tool exercises the real M9/M10 code
path, not a throwaway shim. Installed via the same `pip install .` a
bare-metal Agent host already runs (ADR-004); a new `[project.scripts]`
entry point (`rogue-manual-replay`) makes it directly invokable.

### AIR7201/AIR8201 are the existing `air7311` device family

Confirmed with the user: AIR7201/AIR8201 are SoapySDR-native Deepwave
AIR-T units like the AIR7311, differing only in their SoapySDR driver
string (`device_args`, e.g. `driver=SoapyAIRT` vs. a model-specific
value — ADR-010's addendum already established the AIR7311's exact
string against real hardware). No new adapter class; the CLI's
`device_family` config field stays the existing two-value
`"x440" | "air7311"`, and `PhysicalTxChannelCapability.device_family`'s
`Literal` type is untouched — that field only matters to the
scheduler/compiler, which this standalone CLI never touches.

### Local files only, no catalogue

Confirmed with the user: the CLI reads I/Q strictly from a local
`.sigmf-data`/`.sigmf-meta` pair on the Agent host. `StreamingSDRAdapter.
preflight()` (agents/common/sdr_adapter_base.py) has no such escape
hatch — it only finds recording bytes via `agents.common.cache.
data_path_for`/`meta_path_for`'s naming convention. `stage_local_recording`
(agents/cli/config.py) satisfies that contract from the outside: derive a
stable `uuid5` from the recording's absolute path (fixed namespace, so
repeat runs against the same file are idempotent), then **symlink** —
never copy — the source pair into a scratch cache dir under that naming
convention, and build the `IQRecording` the adapter needs by parsing the
meta file with the existing `rogue.catalogue.sigmf.parse_metadata` (the
same parse `agents/common/agent.py::_load_cached_recording` already does
for a real cache hit). Symlinking rather than copying satisfies CLAUDE.md
rule 7 (never modify/duplicate source recordings) and rule 8 (no loading
large I/Q wholesale) simultaneously, and means the staged file always
reflects the current content at that path — there is no cache-staleness
question.

### A synthetic `RfWindow`/`CompositeChannel`, not a real scenario

`preflight()`/`configure()` need an `RfWindow` with at least one
`CompositeChannel`. With no real scenario, `mission_id`/`link_id`/
`emission_id` are freshly generated `uuid4()`s — structurally required by
the model but never inspected by the adapter layer (only
`center_frequency_hz`/`bandwidth_hz` and each channel's `recording`/
`gain_offset_db` are read). `role` is set to the existing neutral
`RfLinkRole.DATA` value.

### Two entrypoints, because adapter state doesn't survive a process exit

`StreamingSDRAdapter`'s lease/armed/transmitting state lives only in that
adapter instance's memory — there is no cross-process persistence (unlike
the real distributed path, where `AgentRuntime` stays alive as one long
NATS-connected process). A naive CLI with one subprocess invocation per
step (`prepare`, then later `arm`, then later `start`) would silently
lose all state between calls and never actually work. Instead:

- **`run`**: one-shot, single process — the full `prepare → arm → start →
  wait (Ctrl+C or `--duration-seconds`) → stop` cycle, scriptable.
- **`interactive`**: a live session (an `input()`-driven loop, read via
  `asyncio.to_thread` so a background streaming task started by `start`
  keeps running while the loop waits for the next typed command) that
  holds one adapter instance open across separately typed `prepare`/
  `arm`/`start`/`stop`/`status`/`emergency-stop`/`discover` commands —
  the actual step-by-step manual control real bench work needs (e.g.
  checking a spectrum analyzer between `arm` and `start`). Both modes
  always attempt `emergency_stop` in a `finally` block on exit — clean
  quit, `Ctrl+C`, or an unexpected crash mid-session all cut TX the same
  way (CLAUDE.md §10; covered by
  `test_interactive_session_emergency_stops_on_unexpected_exit`).

### Real-TX gate stays the one that already exists

`ROGUE_ENABLE_REAL_TX` (`rogue.settings.settings.enable_real_tx`) is the
same single gate `agents/common/main.py` already uses — no second,
config-file toggle that could drift from it. `device_args` is read from
config if present, else falls back to `ROGUE_X440_DEVICE_ARGS`/
`ROGUE_AIR7311_DEVICE_ARGS`, so a bench host can set it once and every
config file on that host can omit it.

## Consequences

- New files: `agents/cli/__init__.py`, `agents/cli/config.py`,
  `agents/cli/manual_replay.py`; new `[project.scripts]` entry in
  `pyproject.toml`; new `tests/unit/agents/test_manual_replay_cli.py` (12
  tests, all against the same fake `UHDDevice` seam M9's own tests use —
  no real hardware, `ROGUE_ENABLE_REAL_TX` unset by default).
- Nothing in `backend/rogue` changed — no orchestrator, compiler, or
  scenario-domain touch. `PhysicalTxChannelCapability`'s `Literal` is
  unchanged.
- **Known, pre-existing gain-policy gap, not addressed here**: the real
  device's own analog TX gain stays at `StreamingSDRAdapter`'s fixed
  `DEFAULT_GAIN_DB` (0 dB) — unchanged since M9's original docstring
  already flagged "no gain policy beyond each recording's own
  `gain_offset_db`" as a follow-up. The CLI's per-recording
  `gain_offset_db` config field is real (it scales the I/Q samples in
  software before they reach the device, exactly like a compiled
  `ReplayPlan`'s `CompositeChannel.gain_offset_db` does today), but it is
  not a substitute for real per-channel analog gain control. Anyone doing
  RF-loopback bring-up needs to size their attenuators for the adapter's
  fixed default gain, the same constraint M9/M10 hardware verification
  already operates under.
- Not itself hardware-verified — see
  `docs/testing/manual-verification-guide.md`'s new M19 section for the
  worked X440 (`addr=`) and AIR7311/7201/8201 (`driver=`) examples the
  user runs next against their bench hardware.
