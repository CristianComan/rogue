"""Standalone Agent-side CLI to manually prepare/arm/start/stop one real SDR
channel from a local SigMF recording and a small YAML config (M19,
ADR-019).

No backend, database, broker or scenario involved — this talks directly to
`EttusX440Adapter`/`DeepwaveAIR7311Adapter` (the same real hardware
adapters `agents/common/main.py`'s distributed Agent uses for M9/M10), so
bring-up done with this tool exercises the real adapter code path, not a
throwaway shim. Point it at an X440 over the network (``device_args="addr=
..."``) or at a SoapySDR-native Deepwave AIR-T unit run locally on that
unit's own host (AIR7311/AIR7201/AIR8201 — ``device_args="driver=..."``).

Two entrypoints:

- ``run``: one-shot, single process — reserve, preflight, configure, arm,
  start, then block (Ctrl+C or ``--duration-seconds``) before stopping.
  Scriptable; exits after one full cycle.
- ``interactive``: a live session that holds the adapter (and its
  in-memory lease/armed/transmitting state) open across separate typed
  commands (``prepare``/``arm``/``start``/``stop``/``status``/
  ``emergency-stop``) — the step-by-step manual control real bench work
  needs (e.g. checking a spectrum analyzer between ``arm`` and ``start``).
  Adapter state lives only in this process's memory (``StreamingSDRAdapter``
  has no cross-process persistence), which is why step-by-step control has
  to be one long-lived session rather than separate CLI invocations.

``discover`` (adapter.discover()) is available in both modes.

Real TX stays gated by ``ROGUE_ENABLE_REAL_TX`` (`rogue.settings.settings.
enable_real_tx`) exactly as `agents/common/main.py` already gates it —
CLAUDE.md §10's single explicit environment gate, not a second one.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import sys
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import Any

from agents.cli.config import ManualReplayConfig, load_config, stage_local_recording
from agents.common.air7311_adapter import DeepwaveAIR7311Adapter
from agents.common.x440_adapter import EttusX440Adapter
from rogue.compiler.models import CompositeChannel, RfWindow
from rogue.domain.recording import IQRecording
from rogue.domain.rf import RfLinkRole
from rogue.execution.adapter import AdapterOperationError, SDRAdapter
from rogue.settings import settings

INTERACTIVE_HELP = (
    "commands: discover | prepare | arm [start_at_seconds] | start | stop | "
    "status | emergency-stop | run [duration_seconds] | quit"
)


def _print_json(payload: Any) -> None:
    print(json.dumps(payload, indent=2, default=str))


def _device_args_for(config: ManualReplayConfig) -> str:
    if config.device_args:
        return config.device_args
    fallback = (
        settings.x440_device_args
        if config.device_family == "x440"
        else settings.air7311_device_args
    )
    if not fallback:
        env_var = (
            "ROGUE_X440_DEVICE_ARGS"
            if config.device_family == "x440"
            else "ROGUE_AIR7311_DEVICE_ARGS"
        )
        raise SystemExit(
            f"no device_args in config and {env_var} is not set "
            f"for device_family={config.device_family!r}"
        )
    return fallback


def build_adapter(config: ManualReplayConfig) -> SDRAdapter:
    device_args = _device_args_for(config)
    if config.device_family == "x440":
        return EttusX440Adapter(
            capabilities=[],
            cache_dir=config.cache_dir,
            device_args=device_args,
            enable_real_tx=settings.enable_real_tx,
        )
    return DeepwaveAIR7311Adapter(
        capabilities=[],
        cache_dir=config.cache_dir,
        device_args=device_args,
        enable_real_tx=settings.enable_real_tx,
    )


def build_window_and_recordings(config: ManualReplayConfig) -> tuple[RfWindow, list[IQRecording]]:
    """Synthesize the `RfWindow`/`IQRecording`s a real `SDRAdapter` needs,
    standing in for what a compiled `ReplayPlan` would otherwise supply.
    `mission_id`/`link_id`/`emission_id` are structurally required by
    `CompositeChannel` but never read by the adapter layer — only
    frequency/bandwidth/gain and the recording reference are.
    """
    recordings = [stage_local_recording(config.cache_dir, spec.path) for spec in config.recordings]
    channels = [
        CompositeChannel(
            mission_id=uuid.uuid4(),
            link_id=uuid.uuid4(),
            role=RfLinkRole.DATA,
            emission_id=uuid.uuid4(),
            center_frequency_hz=config.center_frequency_hz,
            bandwidth_hz=config.bandwidth_hz,
            gain_offset_db=spec.gain_offset_db,
            recording=recording.reference(),
        )
        for spec, recording in zip(config.recordings, recordings, strict=True)
    ]
    window = RfWindow(
        id=uuid.uuid4(),
        window_key="manual-replay",
        start_seconds=0.0,
        end_seconds=max((r.duration_s for r in recordings), default=0.0),
        center_frequency_hz=config.center_frequency_hz,
        bandwidth_hz=config.bandwidth_hz,
        channels=channels,
    )
    return window, recordings


async def _discover(adapter: SDRAdapter) -> None:
    capabilities = await adapter.discover()
    _print_json([c.model_dump(mode="json") for c in capabilities])


async def _prepare(adapter: SDRAdapter, config: ManualReplayConfig) -> None:
    await adapter.reserve(
        config.device_id, config.channel_index, uuid.uuid4(), config.lease_ttl_seconds
    )
    window, recordings = build_window_and_recordings(config)
    await adapter.preflight(config.device_id, config.channel_index, window, recordings)
    await adapter.configure(config.device_id, config.channel_index, window)


async def _status(adapter: SDRAdapter, config: ManualReplayConfig) -> None:
    status = await adapter.status(config.device_id, config.channel_index)
    _print_json(asdict(status))


async def _run_once(
    adapter: SDRAdapter, config: ManualReplayConfig, duration_seconds: float | None
) -> None:
    await _prepare(adapter, config)
    await adapter.arm(config.device_id, config.channel_index, 0.0)
    await adapter.start(config.device_id, config.channel_index)
    print(
        f"transmitting on {config.device_id}:{config.channel_index} — Ctrl+C to stop"
        + (f", auto-stop after {duration_seconds}s" if duration_seconds is not None else "")
    )
    try:
        if duration_seconds is not None:
            await asyncio.sleep(duration_seconds)
        else:
            await asyncio.Event().wait()
    finally:
        await adapter.stop(config.device_id, config.channel_index)
        print("stopped")


async def _cmd_run(config: ManualReplayConfig, duration_seconds: float | None) -> None:
    adapter = build_adapter(config)
    try:
        await _run_once(adapter, config, duration_seconds)
    finally:
        # Safety net (CLAUDE.md §10): guarantee a stop attempt even if
        # _run_once's own finally didn't get to run cleanly.
        with contextlib.suppress(Exception):
            await adapter.emergency_stop(config.device_id, config.channel_index)


async def _cmd_discover(config: ManualReplayConfig) -> None:
    await _discover(build_adapter(config))


async def _cmd_interactive(config: ManualReplayConfig) -> None:
    await _interactive(build_adapter(config), config)


async def _interactive(adapter: SDRAdapter, config: ManualReplayConfig) -> None:
    print(
        f"manual-replay interactive session — device_id={config.device_id} "
        f"family={config.device_family} channel={config.channel_index}"
    )
    print(INTERACTIVE_HELP)
    try:
        while True:
            try:
                line = (await asyncio.to_thread(input, "> ")).strip()
            except EOFError:
                break
            if not line:
                continue
            name, *args = line.split()
            try:
                if name in ("quit", "exit"):
                    break
                elif name == "discover":
                    await _discover(adapter)
                elif name == "prepare":
                    await _prepare(adapter, config)
                    print("prepared (reserve + preflight + configure ok)")
                elif name == "arm":
                    start_at = float(args[0]) if args else 0.0
                    await adapter.arm(config.device_id, config.channel_index, start_at)
                    print("armed")
                elif name == "start":
                    await adapter.start(config.device_id, config.channel_index)
                    print("start scheduled")
                elif name == "stop":
                    await adapter.stop(config.device_id, config.channel_index)
                    print("stopped")
                elif name == "status":
                    await _status(adapter, config)
                elif name == "emergency-stop":
                    await adapter.emergency_stop(config.device_id, config.channel_index)
                    print("emergency-stopped")
                elif name == "run":
                    duration = float(args[0]) if args else None
                    await _run_once(adapter, config, duration)
                elif name in ("help", "?"):
                    print(INTERACTIVE_HELP)
                else:
                    print(f"unknown command: {name!r} — {INTERACTIVE_HELP}", file=sys.stderr)
            except AdapterOperationError as exc:
                print(f"error: {exc}", file=sys.stderr)
    finally:
        # Safety net on quit/Ctrl+C/any uncaught error: never leave a
        # channel silently transmitting once the session ends.
        with contextlib.suppress(Exception):
            await adapter.emergency_stop(config.device_id, config.channel_index)


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="rogue-manual-replay",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("config", type=Path, help="path to a manual-replay YAML config")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("discover", help="read back the device's real channel capabilities")

    run_parser = subparsers.add_parser("run", help="one-shot: prepare, arm, start, wait, stop")
    run_parser.add_argument(
        "--duration-seconds",
        type=float,
        default=None,
        help="auto-stop after this many seconds (default: run until Ctrl+C)",
    )

    subparsers.add_parser(
        "interactive",
        help="hold the channel open across separate prepare/arm/start/stop/status commands",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    args = _build_arg_parser().parse_args(argv)
    config = load_config(args.config)
    try:
        if args.command == "discover":
            asyncio.run(_cmd_discover(config))
        elif args.command == "run":
            asyncio.run(_cmd_run(config, args.duration_seconds))
        elif args.command == "interactive":
            asyncio.run(_cmd_interactive(config))
    except AdapterOperationError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
