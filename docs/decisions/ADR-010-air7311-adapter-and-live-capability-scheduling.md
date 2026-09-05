# ADR-010: AIR7311 Adapter and Live Capability-Based Scheduling (M10)

**Status:** Accepted baseline — **hardware-unverified**

## Context

Per `docs/architecture/implementation-plan.md`, M10 is "X440 + AIR7311
capability-based scheduling: both hardware families behind common
interface." M9 (ADR-009) delivered `EttusX440Adapter` only. Two gaps
remained:

1. `DeepwaveAIR7311Adapter` didn't exist — "both hardware families" wasn't
   true yet.
2. M6's channel allocator (`rogue/compiler/allocation.py`) already does
   real capability-based routing (tunable range/bandwidth checks per
   channel — CLAUDE.md rule 4's X440 5.15-5.925 GHz exclusion already works
   today), but it only ever schedules against
   `DEFAULT_CAPABILITY_PROFILE`, a compile-time illustrative default —
   never the live capabilities M8's presence-driven agent registry
   (`GET /agents`) already collects from real Agents. CLAUDE.md rule 10
   ("static profiles are defaults only") wasn't actually true in the code.

**Same environment constraint as M9: no SoapySDR bindings and no AIR7311
hardware here.** Unlike `uhd`, SoapySDR's Python bindings are not a normal
pip-installable PyPI package — they're built against the system SoapySDR
C++ library (apt package or built from source), which
`docs/architecture/deployment.md` §7 already flags as bare-metal-host
provisioning outside this repository's packaging. **M10's hardware
verification was not performed here either** — same "code now, verify
later" as M9.

## Decision

- **`DeepwaveAIR7311Adapter`** (`agents/common/air7311_adapter.py`) against
  native SoapySDR per ADR-005. Rather than duplicate M9's adapter logic,
  the vendor-agnostic pieces (lease bookkeeping, the real-TX safety gate,
  bounded-chunk cache-file streaming, cancellation) were extracted from
  `EttusX440Adapter` into a new shared
  `agents/common/sdr_adapter_base.StreamingSDRAdapter` base class,
  parameterized by a `RealDeviceSeam` (renamed from the X440-specific
  `UHDDevice`, same shape, aliased back for readability at each adapter's
  call sites) and a `device_family` label. `EttusX440Adapter` and
  `DeepwaveAIR7311Adapter` are now both thin subclasses supplying only
  `_open_real_uhd_device`/`_open_real_soapy_device`. Same scope limits as
  ADR-009: one physical unit per adapter, one recording per channel,
  `cf32_le` only, no artificial looping.
- **No `pyproject.toml` extra for `SoapySDR`.** Unlike `uhd` (a real,
  versioned PyPI package), there is no equivalent reliable PyPI
  distribution for SoapySDR's Python bindings across platforms — declaring
  one would make `pip install .[air7311]` a broken promise. Provisioning
  instructions (apt package or build-from-source, `SoapySDRUtil --find`)
  go in `docs/testing/manual-verification-guide.md`'s M10 section instead,
  consistent with `deployment.md` §7 already flagging vendor driver
  installation as bare-metal-host software outside ROGUE's own packaging.
  A mypy override (`"SoapySDR.*"` in `ignore_missing_imports`) is still
  added — needed regardless of how/whether it's installed, so mypy doesn't
  choke on the lazy `import SoapySDR`.
- **Live capability-based scheduling.** New
  `rogue.persistence.agents.aggregate_capability_profile(session)` builds
  a `HardwareCapabilityProfile` from every currently-`online` registered
  agent's reported capabilities — the registry doesn't distinguish by
  family, so an X440 agent and an AIR7311 agent both simply contribute
  `PhysicalTxChannelCapability` entries into one combined profile. Returns
  `None` if no agent is online, so `rogue.persistence.replay.
  compile_and_store_replay_plan`'s fallback to `DEFAULT_CAPABILITY_PROFILE`
  stays an explicit decision rather than silently compiling against an
  empty profile that would reject everything. This makes CLAUDE.md rule
  10 ("static profiles are defaults only") actually true: a running
  system with connected Agents schedules against their live, reported
  capabilities; the static default only kicks in when none are online
  (bootstrap, dev, or the test suite's empty-registry transactions).
- **No change to the allocation algorithm itself**
  (`rogue/compiler/allocation.py`) — its capability-based channel
  selection already worked correctly against whatever profile it's given;
  this milestone changes *which* profile is the default, not how
  allocation decides.

## Consequences

- `docs/architecture/implementation-plan.md`'s M10 row is marked "code
  complete, hardware-unverified," same honesty as M9 — the actual exit
  criterion (both families demonstrated on real hardware) needs a lab
  session this environment cannot provide.
- `_open_real_soapy_device`'s exact SoapySDR API calls (`SoapySDR.Device`,
  `setFrequency`/`setSampleRate`/`setBandwidth`/`setGain`,
  `setupStream`/`writeStream`/`activateStream`) are written against
  SoapySDR's documented Python API shape but not exercised against a real
  installation — the first thing a real lab run needs to confirm and
  adjust, same caveat as ADR-009's UHD calls.
- Existing compiler/replay tests are unaffected: they compile inside an
  empty-`sdr_agents` transaction, so `aggregate_capability_profile`
  returns `None` and the static-default fallback preserves today's exact
  behaviour — verified by running the full existing suite, not just
  asserted.
- `EttusX440Adapter`'s public shape is unchanged from ADR-009 (same
  constructor signature, same `UHDDevice` name still importable from
  `x440_adapter.py`) despite the internal refactor onto
  `StreamingSDRAdapter` — existing imports/tests needed no changes beyond
  what M10's own additions required.

## Addendum: real AIR7311 hardware, and a discover()-at-startup fix

While planning an actual connection to a physical AIR7311 (a Deepwave
AIR-T unit — the RF front end is directly attached to an embedded NVIDIA
Jetson/Orin module, which *is* the Agent host per ADR-004, not a separate
PC), `SoapySDRUtil --find` against real hardware confirmed:

```
driver = SoapyAIRT
hardware = AIR7311
serial = 31068155
```

i.e. `ROGUE_AIR7311_DEVICE_ARGS="driver=SoapyAIRT"` is the real, confirmed
device-args string — not a placeholder — and the device enumerates two
daughtercards, matching the 4-TX-channel profile.

Separately, this surfaced a real gap: `agents/common/main.py` built
`AgentRuntime`'s `capabilities` once from `DEFAULT_CAPABILITY_PROFILE`'s
static numbers (filtered by `ROGUE_AGENT_DEVICE_IDS`) and never called
`adapter.discover()` — so a real adapter's presence heartbeat, and
therefore M10's own live-capability-scheduling, would have reported
fabricated illustrative numbers instead of the AIR7311's actual ranges.
Fixed in `AgentRuntime.run()`: capabilities are refreshed from
`self.adapter.discover()` before the first presence publish (a no-op for
`MockSDRAdapter`, which just echoes back what it was already given).

