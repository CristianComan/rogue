"""`replay` CLI entrypoint — matches CLAUDE.md's CLI section:

    replay scan <rec_dir> -o catalog/drones.yaml
    replay validate <scenario.yaml> --catalog catalog/drones.yaml
    replay compile  <scenario.yaml> --catalog ... -o out/
    replay play     <out/name/composite.sigmf-meta> --radio airt7311 [--arm]

`play`'s radio connection info (device_args/channel/tx_gain_db) isn't
repeated on the CLI — `compile` writes it to `radio.json` next to the
composite file, and `play` reads it from there; `--radio` is a safety
cross-check against that file's radio type, not a second way to supply
connection parameters.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from replay_cli.backends.airt import AIRTBackend, play_on_channels
from replay_cli.backends.base import ReplayBackend
from replay_cli.backends.x440 import X440Backend
from replay_cli.catalog_scan import scan_recordings, scan_rogue_corpus, write_catalog
from replay_cli.compile import CompileError, compile_scenario
from replay_cli.schema import RadioType
from replay_cli.validate import validate_scenario_file


def _cmd_scan(args: argparse.Namespace) -> int:
    scan_fn = scan_rogue_corpus if args.layout == "rogue-corpus" else scan_recordings
    result = scan_fn(Path(args.rec_dir))
    write_catalog(result.catalog, Path(args.out))
    print(f"wrote {args.out} ({len(result.catalog.drones)} drone(s))")
    for warning in result.warnings:
        print(f"warning: {warning.where}: {warning.message}")
    return 0


def _cmd_validate(args: argparse.Namespace) -> int:
    issues = validate_scenario_file(Path(args.scenario), Path(args.catalog))
    for issue in issues:
        print(f"{issue.level}: {issue.where}: {issue.message}")
    if not issues:
        print("no issues found")
    return 1 if any(issue.level == "error" for issue in issues) else 0


def _cmd_compile(args: argparse.Namespace) -> int:
    try:
        result = compile_scenario(
            Path(args.scenario),
            Path(args.catalog),
            Path(args.out),
            disk_budget_gb=args.disk_budget_gb,
            ram_budget_gb=args.ram_budget_gb,
            allow_large=args.allow_large,
        )
    except CompileError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"wrote {result.out_dir}")
    for issue in result.issues:
        print(f"{issue.level}: {issue.where}: {issue.message}")
    return 0


def _cmd_play(args: argparse.Namespace) -> int:
    composite_meta = Path(args.composite_meta)
    radio_json_path = composite_meta.parent / "radio.json"
    if not radio_json_path.is_file():
        print(
            f"error: {radio_json_path} not found (expected next to the composite file)",
            file=sys.stderr,
        )
        return 1
    radio = json.loads(radio_json_path.read_text())

    if args.radio is not None and args.radio != radio["type"]:
        print(
            f"error: --radio {args.radio!r} does not match {radio_json_path}'s "
            f"radio type {radio['type']!r}",
            file=sys.stderr,
        )
        return 1

    radio_type = RadioType(radio["type"])

    if args.channels is not None:
        channels = [int(c) for c in args.channels.split(",") if c.strip()]
        if radio_type is RadioType.X440:
            print(
                "error: --channels (multi-channel playback) is only implemented for AIR-T",
                file=sys.stderr,
            )
            return 1
        play_on_channels(
            radio["device_args"],
            channels,
            composite_meta,
            radio["tx_gain_db"],
            args.repeat,
            args.arm,
            tx_attenuation_db=args.tx_attenuation_db,
        )
        return 0

    backend: ReplayBackend
    if radio_type is RadioType.X440:
        backend = X440Backend(radio["device_args"], radio["channel"])
    else:
        backend = AIRTBackend(radio["device_args"], radio["channel"])

    try:
        backend.play(composite_meta, radio["tx_gain_db"], args.repeat, args.arm)
    except NotImplementedError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="replay", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)

    scan_p = sub.add_parser("scan", help="scan a recordings directory into a catalog")
    scan_p.add_argument("rec_dir")
    scan_p.add_argument("-o", "--out", default="catalog/drones.yaml")
    scan_p.add_argument(
        "--layout",
        choices=["simple", "rogue-corpus"],
        default="simple",
        help=(
            "'simple': <rec_dir>/<drone>/<variant>.sigmf-meta. "
            "'rogue-corpus': the main ROGUE repo's own local drone-RF corpus layout "
            "(e.g. recordings/drone-corpus/15June2022) -- variant read from each "
            "recording's own experiment:scenario field, no_drone always skipped."
        ),
    )
    scan_p.set_defaults(func=_cmd_scan)

    validate_p = sub.add_parser("validate", help="validate a scenario against a catalog")
    validate_p.add_argument("scenario")
    validate_p.add_argument("--catalog", required=True)
    validate_p.set_defaults(func=_cmd_validate)

    compile_p = sub.add_parser("compile", help="compile a scenario into one composite SigMF file")
    compile_p.add_argument("scenario")
    compile_p.add_argument("--catalog", required=True)
    compile_p.add_argument("-o", "--out", default="out")
    compile_p.add_argument("--disk-budget-gb", type=float, default=100.0)
    compile_p.add_argument("--ram-budget-gb", type=float, default=4.0)
    compile_p.add_argument("--allow-large", action="store_true")
    compile_p.set_defaults(func=_cmd_compile)

    play_p = sub.add_parser("play", help="play a compiled composite on its radio")
    play_p.add_argument("composite_meta")
    play_p.add_argument(
        "--radio",
        choices=[t.value for t in RadioType],
        default=None,
        help="safety cross-check against radio.json; not a way to supply connection params",
    )
    play_p.add_argument("--arm", action="store_true", help="actually transmit (default: dry run)")
    play_p.add_argument("--repeat", type=int, default=1)
    play_p.add_argument(
        "--channels",
        default=None,
        help=(
            "comma-separated TX channel indices to transmit the SAME composite on "
            "simultaneously (e.g. 0,1,2,3 for a 4-channel direct TX->RX cable loopback "
            "check), overriding radio.json's single channel. AIR-T only."
        ),
    )
    play_p.add_argument(
        "--tx-attenuation-db",
        type=float,
        default=0.0,
        help=(
            "extra software attenuation subtracted from radio.json's tx_gain_db before it "
            "reaches the device -- a direct TX->RX cable has ~0 dB path loss, unlike "
            "over-the-air use, so some extra headroom is usually needed. Independent of, "
            "and in addition to, any hardware inline attenuator."
        ),
    )
    play_p.set_defaults(func=_cmd_play)

    return parser


def main(argv: list[str] | None = None) -> None:
    args = _build_parser().parse_args(argv)
    try:
        exit_code = args.func(args)
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        exit_code = 1
    except ImportError as exc:
        print(
            f"error: {exc} (a real radio backend needs its vendor bindings installed "
            "separately on this host, outside this package's own pip install)",
            file=sys.stderr,
        )
        exit_code = 1
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
