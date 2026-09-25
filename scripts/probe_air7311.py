#!/usr/bin/env python3
"""Read-only AIR7311 capability probe. No TX. No RX stream. No writeStream.

Standalone by design (ADR-019, M19a Phase-0 spike): imports only `SoapySDR`,
not the `rogue`/`agents` packages, so it runs with whatever system Python has
the vendor bindings (see ADR-010/ADR-011 — SoapySDR's Python module is not a
normal pip package and is usually only importable from the system
interpreter, not a project venv).

Usage:
    python3 scripts/probe_air7311.py [device-args]

Default device-args match the confirmed ADR-011 bridge topology: a
SoapyRemote server running on the AIR-T itself (Deepwave AirStack ships this
as a standard apt package), reached from this host over the network.
"""

from __future__ import annotations

import sys

import SoapySDR

DEFAULT_ARGS = "driver=remote,remote=192.168.68.64,remote:driver=SoapyAIRT"


def main() -> None:
    args = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_ARGS
    print(f"Connecting with device args: {args}\n")
    dev = SoapySDR.Device(args)

    hw_info = dev.getHardwareInfo()
    print("== Hardware info ==")
    for key, value in sorted(hw_info.items()):
        print(f"  {key}: {value}")

    num_tx = dev.getNumChannels(SoapySDR.SOAPY_SDR_TX)
    num_rx = dev.getNumChannels(SoapySDR.SOAPY_SDR_RX)
    print(f"\nTX channels: {num_tx}")
    print(f"RX channels: {num_rx}")

    master_rates = dev.getMasterClockRates()
    print(f"\nMaster clock rates available: "
          f"{[(r.minimum(), r.maximum()) for r in master_rates]}")
    print(f"Master clock rate (current): {dev.getMasterClockRate()}")

    clock_sources = dev.listClockSources()
    time_sources = dev.listTimeSources()
    print(f"Clock sources: {clock_sources} (current: {dev.getClockSource()})")
    print(f"Time sources: {time_sources} (current: {dev.getTimeSource()})")

    for direction, label, count in (
        (SoapySDR.SOAPY_SDR_TX, "TX", num_tx),
        (SoapySDR.SOAPY_SDR_RX, "RX", num_rx),
    ):
        for ch in range(count):
            print(f"\n== {label} channel {ch} ==")
            print(f"  antennas: {dev.listAntennas(direction, ch)} "
                  f"(current: {dev.getAntenna(direction, ch)})")
            freq_ranges = dev.getFrequencyRange(direction, ch)
            print(f"  frequency ranges (Hz): "
                  f"{[(r.minimum(), r.maximum()) for r in freq_ranges]}")
            rate_ranges = dev.getSampleRateRange(direction, ch)
            if rate_ranges:
                print(f"  sample rate ranges (Sps): "
                      f"{[(r.minimum(), r.maximum()) for r in rate_ranges]}")
            else:
                print(f"  sample rates (discrete, Sps): {dev.listSampleRates(direction, ch)}")
            bw_ranges = dev.getBandwidthRange(direction, ch)
            print(f"  bandwidth ranges (Hz): "
                  f"{[(r.minimum(), r.maximum()) for r in bw_ranges]}")
            gain_range = dev.getGainRange(direction, ch)
            print(f"  overall gain range (dB): "
                  f"[{gain_range.minimum()}, {gain_range.maximum()}]")
            for gain_name in dev.listGains(direction, ch):
                gr = dev.getGainRange(direction, ch, gain_name)
                print(f"    gain element {gain_name!r}: "
                      f"[{gr.minimum()}, {gr.maximum()}] step={gr.step()}")
            formats = dev.getStreamFormats(direction, ch)
            print(f"  stream formats: {formats}")

    print(f"\nhasHardwareTime: {dev.hasHardwareTime()}")

    print("\nNo TX keyed. No stream opened. Probe complete.")


if __name__ == "__main__":
    main()
