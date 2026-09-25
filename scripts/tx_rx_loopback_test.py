#!/usr/bin/env python3
"""Manual, single-channel TX->RX cabled loopback sanity test for the AIR7311.

Standalone by design (ADR-019 Phase-0 spike, same reasoning as
probe_air7311.py): only imports SoapySDR + numpy, runs under system
python3, no rogue/agents package dependency.

Safety posture (CLAUDE.md rule 10.5 - "start hardware testing with maximum
TX attenuation or minimum TX gain and low digital amplitude"): this script
queries the *live* gain floor from the device rather than hardcoding one
(the AIR7311's only gain element is a single "Digital" stage where 0 dB is
MAXIMUM output - the opposite of an attenuator-style control), defaults to
that floor for both TX and RX, and defaults the digital waveform amplitude
low. TX is never keyed without --confirm-tx on the command line - this is a
real transmitter into a bare direct cable (no inline attenuator), not a
simulation.

What it does:
  1. Connects to the device (read-only queries only, same as probe_air7311.py).
  2. Configures RX on the given channel at the live gain floor, starts a
     capture stream FIRST so it is already listening before TX fires.
  3. Configures TX on the same channel index at the live gain floor.
  4. Generates a short, low-amplitude complex tone offset from DC (not at
     DC, not at the band edge - avoids the LO-leakage/DC-spike region).
  5. Transmits the tone once, captures the RX samples concurrently.
  6. Reports peak/RMS level (dBFS), clipping, and the measured tone
     frequency offset via FFT peak - the same checks Loop Test 1's first
     steps call for, just run by hand instead of from a scenario file.

Usage:
    python3 scripts/tx_rx_loopback_test.py --channel 0 --confirm-tx

Without --confirm-tx, the script configures everything and prints what it
WOULD do, then exits without opening a TX stream.
"""

from __future__ import annotations

import argparse
import sys

import numpy as np
import SoapySDR

DEFAULT_ARGS = "driver=remote,remote=192.168.68.64,remote:driver=SoapyAIRT"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--device-args", default=DEFAULT_ARGS)
    p.add_argument("--channel", type=int, default=0, help="TX and RX channel index (0-3); cabled 1-1/2-2/3-3/4-4 means TX ch N loops to RX ch N")
    p.add_argument("--freq-hz", type=float, default=1.0e9, help="center frequency for both TX and RX")
    p.add_argument("--sample-rate-hz", type=float, default=2_000_000.0, help="must fall in one of the device's discrete sample-rate ranges")
    p.add_argument("--master-clock-hz", type=float, default=64_000_000.0, help="must be set to a value compatible with --sample-rate-hz before any channel is configured (device-enforced; see the AIR7311 clocking docs)")
    p.add_argument("--tone-offset-hz", type=float, default=None, help="tone offset from center; default sample_rate/8, away from DC")
    p.add_argument("--amplitude", type=float, default=0.02, help="digital full-scale fraction (0-1) of the transmitted tone")
    p.add_argument("--num-samples", type=int, default=4_000, help="kept small by default to minimize TX-on duration for a first live attempt")
    p.add_argument("--confirm-tx", action="store_true", help="actually key the transmitter; without this flag, configures everything and exits before TX")
    return p.parse_args()


def report_gain_floor(dev: SoapySDR.Device, direction: int, channel: int, label: str) -> float:
    gain_range = dev.getGainRange(direction, channel)
    floor_db = gain_range.minimum()
    print(f"  {label} live gain range: [{gain_range.minimum()}, {gain_range.maximum()}] dB "
          f"-> using floor {floor_db} dB")
    return floor_db


def configure_channel(dev: SoapySDR.Device, direction: int, channel: int, freq_hz: float,
                       rate_hz: float, gain_db: float, label: str) -> None:
    dev.setSampleRate(direction, channel, rate_hz)
    dev.setFrequency(direction, channel, freq_hz)
    dev.setGain(direction, channel, gain_db)
    applied_rate = dev.getSampleRate(direction, channel)
    applied_freq = dev.getFrequency(direction, channel)
    applied_gain = dev.getGain(direction, channel)
    print(f"  {label} ch{channel}: requested rate={rate_hz} freq={freq_hz} gain={gain_db} dB")
    print(f"  {label} ch{channel}: applied   rate={applied_rate} freq={applied_freq} gain={applied_gain} dB")
    if abs(applied_rate - rate_hz) > 1.0:
        print(f"  WARNING: applied sample rate differs from requested - "
              f"{rate_hz} Hz is likely outside a supported discrete range for this device")


def make_tone(num_samples: int, sample_rate_hz: float, offset_hz: float, amplitude: float) -> np.ndarray:
    t = np.arange(num_samples) / sample_rate_hz
    tone = amplitude * np.exp(2j * np.pi * offset_hz * t)
    return tone.astype(np.complex64)


def analyze_capture(samples: np.ndarray, sample_rate_hz: float, expected_offset_hz: float) -> None:
    if samples.size == 0:
        print("  No samples captured - RX stream produced nothing.")
        return
    peak = float(np.max(np.abs(samples)))
    rms = float(np.sqrt(np.mean(np.abs(samples) ** 2)))
    peak_dbfs = 20 * np.log10(peak) if peak > 0 else float("-inf")
    rms_dbfs = 20 * np.log10(rms) if rms > 0 else float("-inf")
    clipped = np.sum(np.abs(samples) >= 0.999)
    print(f"  captured {samples.size} samples")
    print(f"  peak = {peak:.4f} ({peak_dbfs:.1f} dBFS), rms = {rms:.4f} ({rms_dbfs:.1f} dBFS)")
    print(f"  clipped samples (>=0.999 full scale): {clipped}")
    if clipped > 0:
        print("  WARNING: clipping detected even at the gain floor - do not raise gain; "
              "add a physical inline attenuator before any further testing.")

    spectrum = np.fft.fftshift(np.fft.fft(samples))
    freqs = np.fft.fftshift(np.fft.fftfreq(samples.size, d=1.0 / sample_rate_hz))
    peak_bin = int(np.argmax(np.abs(spectrum)))
    measured_offset_hz = float(freqs[peak_bin])
    print(f"  strongest FFT bin at {measured_offset_hz:,.0f} Hz offset "
          f"(expected ~{expected_offset_hz:,.0f} Hz)")
    if abs(measured_offset_hz - expected_offset_hz) > sample_rate_hz * 0.02:
        print("  WARNING: measured tone offset does not match what was transmitted - "
              "check channel mapping / cabling (is this really TX{ch}->RX{ch}?).")
    else:
        print("  Tone recovered at the expected offset - loopback path confirmed.")


def main() -> None:
    args = parse_args()
    offset_hz = args.tone_offset_hz if args.tone_offset_hz is not None else args.sample_rate_hz / 8

    print(f"Connecting with device args: {args.device_args}\n")
    dev = SoapySDR.Device(args.device_args)

    print(f"== Master clock rate (must be set while idle, before any channel config) ==")
    dev.setMasterClockRate(args.master_clock_hz)
    applied_mcr = dev.getMasterClockRate()
    print(f"  requested {args.master_clock_hz:,.0f} Hz, applied {applied_mcr:,.0f} Hz")
    if abs(applied_mcr - args.master_clock_hz) > 1.0:
        print("  WARNING: applied master clock rate differs from requested.")

    print("\n== RX setup (started before TX, so it is already listening) ==")
    rx_floor_db = report_gain_floor(dev, SoapySDR.SOAPY_SDR_RX, args.channel, "RX")
    configure_channel(dev, SoapySDR.SOAPY_SDR_RX, args.channel, args.freq_hz,
                       args.sample_rate_hz, rx_floor_db, "RX")

    print("\n== TX setup ==")
    tx_floor_db = report_gain_floor(dev, SoapySDR.SOAPY_SDR_TX, args.channel, "TX")
    configure_channel(dev, SoapySDR.SOAPY_SDR_TX, args.channel, args.freq_hz,
                       args.sample_rate_hz, tx_floor_db, "TX")

    tone = make_tone(args.num_samples, args.sample_rate_hz, offset_hz, args.amplitude)
    print(f"\nGenerated tone: {args.num_samples} samples, offset {offset_hz:,.0f} Hz, "
          f"amplitude {args.amplitude} full-scale")

    if not args.confirm_tx:
        print("\n--confirm-tx not given. Everything above is configured on the live device "
              "(gain/freq/rate are now set) but no stream was opened and no TX was keyed. "
              "Re-run with --confirm-tx to actually transmit and capture.")
        return

    # Every blocking SoapySDR call below gets an explicit, finite timeoutUs -
    # a stalled network transport must return an error, never hang forever -
    # and every stream is torn down in `finally` so a raised exception (or a
    # bounded-timeout return) can never leave TX keyed.
    write_timeout_us = 3_000_000
    read_timeout_us = 3_000_000
    captured = np.zeros(0, dtype=np.complex64)

    print("\n== Opening RX stream and arming capture ==")
    rx_stream = dev.setupStream(SoapySDR.SOAPY_SDR_RX, "CF32", [args.channel])
    rx_buffer = np.zeros(args.num_samples + int(args.sample_rate_hz) // 1000, dtype=np.complex64)
    try:
        dev.activateStream(rx_stream)

        print("== Opening TX stream and transmitting once ==")
        tx_stream = dev.setupStream(SoapySDR.SOAPY_SDR_TX, "CF32", [args.channel])
        try:
            dev.activateStream(tx_stream)
            tx_result = dev.writeStream(
                tx_stream, [tone], tone.size,
                flags=SoapySDR.SOAPY_SDR_END_BURST, timeoutUs=write_timeout_us,
            )
            print(f"  writeStream result: ret={tx_result.ret} flags={tx_result.flags}")
            if tx_result.ret < 0:
                print(f"  WARNING: writeStream did not report full success "
                      f"(requested {tone.size} samples) - treat this capture as unreliable.")
        finally:
            dev.deactivateStream(tx_stream)
            dev.closeStream(tx_stream)
            print("  TX stream deactivated and closed - transmitter is no longer keyed.")

        print("== Reading back RX capture ==")
        read = dev.readStream(rx_stream, [rx_buffer], rx_buffer.size, timeoutUs=read_timeout_us)
        print(f"  readStream result: ret={read.ret} flags={read.flags}")
        captured = rx_buffer[: max(read.ret, 0)]
    finally:
        dev.deactivateStream(rx_stream)
        dev.closeStream(rx_stream)

    print("\n== Analysis ==")
    analyze_capture(captured, args.sample_rate_hz, offset_hz)


if __name__ == "__main__":
    main()
