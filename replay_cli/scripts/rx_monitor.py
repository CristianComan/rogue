#!/usr/bin/env python3
"""RX waterfall monitor for an AIR-T unit — run this locally, on the AIR-T.

Continuously receives on each listed RX channel (default 0,1,2,3) and
writes one PNG (a waterfall panel per channel, time x frequency, dB),
refreshed periodically. Headless (matplotlib's Agg backend) since the
AIR-T is normally accessed over SSH with no display attached — pull the
PNG over (e.g. `scp`, or your already-synced replay_cli folder) to view
it, or open it from an editor/file manager pointed at the host.

Run this in one terminal/session while `replay play --channels ...`
(see `src/replay_cli/backends/airt.py::play_on_channels`) runs in
another — each RX channel's waterfall should show live signal once its
corresponding TX channel starts transmitting, confirming that TX->RX
pair is alive.

    .venv/bin/python scripts/rx_monitor.py --device-args "driver=SoapyAIRT" \\
        --channels 0,1,2,3 --out waterfall.png
"""

from __future__ import annotations

import argparse
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import matplotlib  # noqa: E402 - sys.path must be set up first

matplotlib.use("Agg")  # headless: see module docstring
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from replay_cli.rx_monitor import (  # noqa: E402
    ChannelWaterfall,
    open_real_soapy_rx_device,
    receiver_loop,
)


def _save_waterfall_png(
    waterfalls: dict[int, ChannelWaterfall],
    channels: list[int],
    freqs_mhz: np.ndarray,
    out_path: Path,
) -> None:
    fig, axes = plt.subplots(1, len(channels), figsize=(4.5 * len(channels), 5), squeeze=False)
    for ax, channel in zip(axes[0], channels, strict=True):
        waterfall = waterfalls[channel]
        ax.imshow(
            waterfall.rows,
            aspect="auto",
            origin="lower",
            extent=[freqs_mhz[0], freqs_mhz[-1], 0, waterfall.history],
            vmin=-100,
            vmax=20,
        )
        ax.set_title(f"RX{channel}")
        ax.set_xlabel("MHz")
    axes[0][0].set_ylabel("time (newest row at top)")
    fig.tight_layout()
    fig.savefig(out_path)
    plt.close(fig)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--device-args", default="driver=SoapyAIRT")
    parser.add_argument("--channels", default="0,1,2,3", help="comma-separated RX channel indices")
    parser.add_argument("--center-freq-hz", type=float, default=2_450_000_000.0)
    parser.add_argument("--rate-hz", type=float, default=10_000_000.0)
    parser.add_argument("--rx-gain-db", type=float, default=0.0)
    parser.add_argument("--fft-size", type=int, default=1024)
    parser.add_argument("--history", type=int, default=200, help="waterfall rows kept per channel")
    parser.add_argument("--refresh-interval-s", type=float, default=1.0)
    parser.add_argument(
        "--duration-s",
        type=float,
        default=None,
        help="stop after this long (default: until Ctrl+C)",
    )
    parser.add_argument("--out", default="waterfall.png")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    channels = [int(c) for c in args.channels.split(",") if c.strip()]

    print(
        f"opening {args.device_args!r}, channels={channels}, writing {args.out} every "
        f"{args.refresh_interval_s}s -- Ctrl+C to stop"
    )
    device = open_real_soapy_rx_device(args.device_args)

    waterfalls = {channel: ChannelWaterfall(args.fft_size, args.history) for channel in channels}
    stop = threading.Event()
    threads = [
        threading.Thread(
            target=receiver_loop,
            args=(device, channel),
            kwargs={
                "freq_hz": args.center_freq_hz,
                "rate_hz": args.rate_hz,
                "gain_db": args.rx_gain_db,
                "chunk_samples": args.fft_size,
                "waterfall": waterfalls[channel],
                "stop": stop,
            },
            daemon=True,
        )
        for channel in channels
    ]
    for thread in threads:
        thread.start()

    freqs_mhz = (
        np.fft.fftshift(np.fft.fftfreq(args.fft_size, d=1 / args.rate_hz)) / 1e6
        + args.center_freq_hz / 1e6
    )

    start = time.monotonic()
    try:
        while True:
            time.sleep(args.refresh_interval_s)
            _save_waterfall_png(waterfalls, channels, freqs_mhz, Path(args.out))
            if args.duration_s is not None and time.monotonic() - start >= args.duration_s:
                break
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        for thread in threads:
            thread.join(timeout=5)

    print(f"stopped; last snapshot written to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
