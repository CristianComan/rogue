#!/usr/bin/env python3
"""RF loopback self-test for an AIR-T unit — run this locally, on the AIR-T.

Connect each TX channel to its correspondingly-numbered RX channel with
a cable (TX0->RX0, TX1->RX1, TX2->RX2, TX3->RX3 for a 4-channel AIR-T
unit — two AD9371s). Transmits a known tone on each TX channel in turn
and checks it arrives on that channel's RX with the expected frequency
and adequate SNR, catching dead channels, swapped cabling, and bad
connectors before trusting the hardware for anything else.

See `src/replay_cli/loopback.py` for the actual check/analysis logic
and its safety note on direct-cable-loopback gain — **fit an inline
attenuator between every TX/RX pair before using --arm**; a direct
cable has ~0 dB path loss, unlike over-the-air use.

Dry run first (no radio opened, nothing transmitted; --max-tx-gain-db is
always required, even here, since it's validated before anything else):

    .venv/bin/python scripts/loopback_check.py --max-tx-gain-db 0

Then, with attenuators fitted and `--arm`:

    .venv/bin/python scripts/loopback_check.py --device-args "driver=SoapyAIRT" \\
        --tx-gain-db -10 --max-tx-gain-db -10 --arm
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from replay_cli.loopback import (  # noqa: E402 - sys.path must be set up first
    SAFETY_BANNER,
    LoopbackResult,
    open_real_soapy_loopback_device,
    run_channel_loopback,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--device-args", default="driver=SoapyAIRT")
    parser.add_argument(
        "--channels", default="0,1,2,3", help="comma-separated TX/RX channel indices to test"
    )
    parser.add_argument("--center-freq-hz", type=float, default=2_450_000_000.0)
    parser.add_argument("--rate-hz", type=float, default=10_000_000.0)
    parser.add_argument("--num-samples", type=int, default=65536)
    parser.add_argument("--tx-gain-db", type=float, default=0.0)
    parser.add_argument(
        "--max-tx-gain-db",
        type=float,
        required=True,
        help="mandatory safety cap -- refuses --tx-gain-db above this",
    )
    parser.add_argument("--rx-gain-db", type=float, default=0.0)
    parser.add_argument(
        "--arm", action="store_true", help="actually transmit (default: dry run, no radio opened)"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    if args.tx_gain_db > args.max_tx_gain_db:
        print(
            f"error: --tx-gain-db {args.tx_gain_db} exceeds --max-tx-gain-db {args.max_tx_gain_db}",
            file=sys.stderr,
        )
        return 1

    channels = [int(c) for c in args.channels.split(",") if c.strip()]

    print(
        f"plan: device_args={args.device_args!r} channels={channels} "
        f"center_freq_hz={args.center_freq_hz:.0f} rate_hz={args.rate_hz:.0f} "
        f"tx_gain_db={args.tx_gain_db} rx_gain_db={args.rx_gain_db}"
    )
    if not args.arm:
        print(
            "[dry run] no radio opened, nothing transmitted. Pass --arm to actually run the test."
        )
        return 0

    print(SAFETY_BANNER)
    if input("Type 'yes' to transmit: ").strip().lower() != "yes":
        print("not confirmed; aborting, no transmit.")
        return 1

    device = open_real_soapy_loopback_device(args.device_args)

    results: list[LoopbackResult] = []
    for channel in channels:
        result = run_channel_loopback(
            device,
            channel,
            freq_hz=args.center_freq_hz,
            rate_hz=args.rate_hz,
            tx_gain_db=args.tx_gain_db,
            rx_gain_db=args.rx_gain_db,
            num_samples=args.num_samples,
        )
        results.append(result)
        print(
            f"channel {result.channel}: {'PASS' if result.passed else 'FAIL'} -- {result.message}"
        )

    passed = sum(r.passed for r in results)
    print(f"\n{passed}/{len(results)} channels passed")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
