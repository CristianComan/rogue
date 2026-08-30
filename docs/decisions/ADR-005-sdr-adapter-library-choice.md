# ADR-005: SDR Adapters Stay Split by Vendor Library, Not Unified on SoapySDR

**Status:** Accepted baseline

## Context

The AIR7311 is SoapySDR-native. The X440 is normally driven through UHD, but
Ettus USRPs can also be reached through SoapySDR via the `SoapyUHD` wrapper
module. This raises two questions: whether to access either device remotely
over the network at the vendor-library level, and whether to standardize both
adapters on a single library (SoapySDR, via `SoapyUHD` for the X440) instead
of maintaining separate UHD and Soapy code paths.

## Decision

1. **No production remote access at the vendor-library level.** `SoapyRemote`
   (or an equivalent network transport for a vendor library) is diagnostics-
   only. Production access to a device is always through the SDR Agent
   running bare-metal, adjacent to that device (ADR-004), talking to the
   control plane over ROGUE's own versioned Agent protocol — never a
   vendor-library RPC tunnel.
2. **Keep `EttusX440Adapter` on native UHD and `DeepwaveAIR7311Adapter` on
   native SoapySDR**, per `sdr-architecture.md` §2, rather than collapsing
   both onto SoapySDR via `SoapyUHD`. The shared `SDRAdapter` Protocol is
   where cross-vendor consistency lives, not the underlying driver library.

## Rationale

- ADR-004 puts each Agent physically next to its hardware specifically to
  protect access to shared timing references (PPS/10 MHz/PTP) for the L3/L4
  synchronization classes (`sdr-architecture.md` §5). Remoting the vendor
  API over IP (what `SoapyRemote` does) reintroduces the network jitter that
  decision exists to avoid.
- `SoapyUHD`'s coverage of newer/advanced UHD functionality (GPSDO/PPS/PTP
  timed commands, RFNoC) has historically lagged native UHD, and the X440 is
  a newer X4xx-series device. The M11 multi-SDR synchronization milestone
  needs full access to those capabilities; a generic wrapper risks a
  capability ceiling exactly where precision matters most.
- The AIR7311 carries no equivalent advanced-synchronization requirement, so
  native SoapySDR access for it is unaffected by this decision.
- `SDRAdapter` (the vendor-neutral Protocol in `sdr-architecture.md` §2) is
  the layer CLAUDE.md rule 3 already designates for cross-vendor
  consistency. Unifying at the library level instead would duplicate that
  purpose without displacing the need for the Protocol.

## Consequences

- `EttusX440Adapter` (M9/M10) is written against UHD's native Python
  bindings, not `SoapyUHD`.
- `SoapyUHD` remains an available fallback for early/basic X440 streaming
  (e.g. a first cut during M9) if native UHD integration proves slow, but is
  not the target for the finished adapter.
- `SoapyRemote` may still be used ad hoc for bench diagnostics (e.g.
  confirming an AIR7311 is enumerable from a workstation), but must not be
  wired into any Agent, orchestration, or Replay Plan execution path.
- This decision does not change scenario authoring: `ResourcePreference`
  (ADR-002) remains the only hardware-adjacent input a scenario may express,
  and stays non-binding regardless of which library eventually executes it.
