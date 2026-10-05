"""Tests for the manual replay CLI (M19, ADR-019) — config parsing, local
recording staging, synthetic RfWindow construction, and command dispatch
against fake `UHDDevice`/`SoapyDevice` seams (reusing the same fakes M9/M10
already test the real adapters against). No real hardware, no real TX
(CLAUDE.md §10's simulation default) — `ROGUE_ENABLE_REAL_TX` stays unset
throughout.
"""

from __future__ import annotations

import json
import struct
from dataclasses import dataclass, field
from pathlib import Path

import pytest
import yaml
from agents.cli import manual_replay
from agents.cli.config import ManualReplayConfig, load_config, stage_local_recording
from agents.common.x440_adapter import (
    ChannelCapabilityReadback,
    ChannelConfig,
    EttusX440Adapter,
    RealTxNotAuthorizedError,
)

DEVICE_ID = "x440-bench"
CHANNEL = 0


@dataclass
class _FakeUHDDevice:
    configured: dict[int, dict[str, float]] = field(default_factory=dict)
    sent_chunks: dict[int, list[bytes]] = field(default_factory=dict)
    ended_bursts: list[int] = field(default_factory=list)

    def num_tx_channels(self) -> int:
        return 8

    def discover_channel(self, channel: int) -> ChannelCapabilityReadback:
        return ChannelCapabilityReadback(
            tunable_ranges_hz=[(1e6, 6e9)], max_usable_bandwidth_hz=400e6, max_sample_rate_hz=500e6
        )

    def configure_channel(
        self, channel: int, *, freq_hz: float, rate_hz: float, bandwidth_hz: float, gain_db: float
    ) -> None:
        self.configured[channel] = {
            "freq_hz": freq_hz,
            "rate_hz": rate_hz,
            "bandwidth_hz": bandwidth_hz,
            "gain_db": gain_db,
        }

    def read_channel_config(self, channel: int) -> ChannelConfig:
        cfg = self.configured.get(channel, {})
        return ChannelConfig(
            freq_hz=cfg.get("freq_hz", 0.0),
            rate_hz=cfg.get("rate_hz", 0.0),
            bandwidth_hz=cfg.get("bandwidth_hz", 0.0),
            gain_db=cfg.get("gain_db", 0.0),
        )

    def send_chunk(self, channel: int, samples: object) -> None:
        self.sent_chunks.setdefault(channel, []).append(bytes(samples))  # type: ignore[call-overload]

    def end_burst(self, channel: int) -> None:
        self.ended_bursts.append(channel)


def _write_recording(
    dir_: Path, name: str, *, sample_count: int = 8, sample_rate_hz: float = 1_000_000.0
) -> Path:
    data_path = dir_ / f"{name}.sigmf-data"
    meta_path = dir_ / f"{name}.sigmf-meta"
    with data_path.open("wb") as f:
        for i in range(sample_count):
            f.write(struct.pack("<ff", 0.001 * i, -0.001 * i))
    meta_path.write_text(
        json.dumps(
            {
                "global": {
                    "core:datatype": "cf32_le",
                    "core:sample_rate": sample_rate_hz,
                },
                "captures": [{"core:frequency": 2_412_000_000.0, "core:sample_start": 0}],
            }
        )
    )
    return data_path


def make_config(tmp_path: Path, recording_path: Path, **overrides: object) -> ManualReplayConfig:
    kwargs: dict[str, object] = {
        "device_family": "x440",
        "device_args": "addr=192.0.2.10",
        "device_id": DEVICE_ID,
        "channel_index": CHANNEL,
        "center_frequency_hz": 2_412_000_000.0,
        "bandwidth_hz": 20_000_000.0,
        "recordings": [{"path": str(recording_path)}],
        "cache_dir": tmp_path / "cache",
    }
    kwargs.update(overrides)
    return ManualReplayConfig.model_validate(kwargs)


def make_adapter(
    config: ManualReplayConfig, *, enable_real_tx: bool = True
) -> tuple[EttusX440Adapter, _FakeUHDDevice]:
    device = _FakeUHDDevice()
    adapter = EttusX440Adapter(
        capabilities=[],
        cache_dir=config.cache_dir,
        device=device,
        enable_real_tx=enable_real_tx,
    )
    return adapter, device


# --- config loading -----------------------------------------------------


def test_load_config_parses_yaml(tmp_path: Path) -> None:
    recording_path = _write_recording(tmp_path, "drone1")
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "device_family": "air7311",
                "device_args": "driver=SoapyAIRT",
                "channel_index": 1,
                "center_frequency_hz": 5_800_000_000.0,
                "bandwidth_hz": 10_000_000.0,
                "recordings": [{"path": str(recording_path), "gain_offset_db": -3.0}],
            }
        )
    )

    config = load_config(config_path)

    assert config.device_family == "air7311"
    assert config.channel_index == 1
    assert config.recordings[0].gain_offset_db == -3.0
    assert config.recordings[0].path == recording_path.resolve()


def test_config_rejects_unknown_device_family(tmp_path: Path) -> None:
    recording_path = _write_recording(tmp_path, "drone1")
    with pytest.raises(Exception):  # noqa: B017 - pydantic ValidationError
        make_config(tmp_path, recording_path, device_family="air9999")


# --- local recording staging --------------------------------------------


def test_stage_local_recording_symlinks_without_copying(tmp_path: Path) -> None:
    recording_path = _write_recording(tmp_path, "drone1", sample_count=4)
    cache_dir = tmp_path / "cache"

    recording = stage_local_recording(cache_dir, recording_path)

    from agents.common import cache

    staged_data = cache.data_path_for(cache_dir, recording.id, recording.version)
    assert staged_data.is_symlink()
    assert staged_data.resolve() == recording_path.resolve()
    assert recording.sample_format == "cf32_le"
    assert recording.sample_rate_hz == 1_000_000.0
    assert recording.sample_count == 4
    assert recording.center_frequency_hz == 2_412_000_000.0


def test_stage_local_recording_is_idempotent_across_calls(tmp_path: Path) -> None:
    recording_path = _write_recording(tmp_path, "drone1")
    cache_dir = tmp_path / "cache"

    first = stage_local_recording(cache_dir, recording_path)
    second = stage_local_recording(cache_dir, recording_path)

    assert first.id == second.id  # same source path -> same derived id


def test_stage_local_recording_rejects_missing_meta_sibling(tmp_path: Path) -> None:
    data_path = tmp_path / "orphan.sigmf-data"
    data_path.write_bytes(b"\x00" * 32)

    with pytest.raises(FileNotFoundError):
        stage_local_recording(tmp_path / "cache", data_path)


# --- window synthesis + command dispatch against a fake device ----------


async def test_prepare_then_start_streams_the_staged_recording(tmp_path: Path) -> None:
    recording_path = _write_recording(tmp_path, "drone1", sample_count=4)
    config = make_config(tmp_path, recording_path)
    adapter, device = make_adapter(config, enable_real_tx=True)

    await manual_replay._prepare(adapter, config)
    assert device.configured[CHANNEL]["freq_hz"] == config.center_frequency_hz

    await adapter.arm(config.device_id, config.channel_index, 0.0)
    await adapter.start(config.device_id, config.channel_index)
    stream_task = adapter._state(CHANNEL).stream_task
    assert stream_task is not None
    await stream_task  # let the (tiny, 4-sample) recording finish streaming

    assert CHANNEL in device.sent_chunks
    assert CHANNEL in device.ended_bursts

    await adapter.stop(config.device_id, config.channel_index)


async def test_run_without_enable_real_tx_refuses_to_key(tmp_path: Path) -> None:
    recording_path = _write_recording(tmp_path, "drone1")
    config = make_config(tmp_path, recording_path)
    adapter, device = make_adapter(config, enable_real_tx=False)

    with pytest.raises(RealTxNotAuthorizedError):
        await manual_replay._run_once(adapter, config, duration_seconds=0.0)

    assert device.sent_chunks == {}


async def test_discover_prints_real_device_capabilities(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    recording_path = _write_recording(tmp_path, "drone1")
    config = make_config(tmp_path, recording_path)
    adapter, _device = make_adapter(config)

    await manual_replay._discover(adapter)

    printed = json.loads(capsys.readouterr().out)
    assert printed[0]["device_family"] == "x440"
    assert printed[0]["max_usable_bandwidth_hz"] == 400e6


async def test_status_reports_not_configured_before_prepare(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    recording_path = _write_recording(tmp_path, "drone1")
    config = make_config(tmp_path, recording_path)
    adapter, _device = make_adapter(config)

    await manual_replay._status(adapter, config)

    printed = json.loads(capsys.readouterr().out)
    assert printed["configured"] is False
    assert printed["transmitting"] is False


async def test_interactive_prepare_arm_start_stop_quit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    recording_path = _write_recording(tmp_path, "drone1", sample_count=4)
    config = make_config(tmp_path, recording_path)
    adapter, device = make_adapter(config, enable_real_tx=True)

    commands = iter(["prepare", "arm", "start", "stop", "quit"])

    def fake_input(_prompt: str) -> str:
        return next(commands)

    monkeypatch.setattr("builtins.input", fake_input)

    await manual_replay._interactive(adapter, config)

    status_after = await adapter.status(config.device_id, config.channel_index)
    assert status_after.transmitting is False
    assert "prepared" in capsys.readouterr().out


async def test_interactive_session_emergency_stops_on_unexpected_exit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The session's own `finally` must cut TX even if the loop exits via an
    uncaught exception rather than a clean `quit` — the same discipline
    CLAUDE.md §10 requires dedicated emergency-stop coverage for.
    """
    recording_path = _write_recording(tmp_path, "drone1", sample_count=200_000)
    config = make_config(tmp_path, recording_path)
    adapter, device = make_adapter(config, enable_real_tx=True)

    commands = iter(["prepare", "arm", "start"])

    def fake_input(_prompt: str) -> str:
        try:
            return next(commands)
        except StopIteration:
            raise RuntimeError("simulated unexpected session crash") from None

    monkeypatch.setattr("builtins.input", fake_input)

    with pytest.raises(RuntimeError, match="simulated unexpected session crash"):
        await manual_replay._interactive(adapter, config)

    status_after = await adapter.status(config.device_id, config.channel_index)
    assert status_after.transmitting is False
    assert status_after.armed is False


def test_device_args_falls_back_to_settings_env_when_config_omits_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    recording_path = _write_recording(tmp_path, "drone1")
    config = make_config(tmp_path, recording_path, device_args=None)

    from rogue.settings import settings

    monkeypatch.setattr(settings, "x440_device_args", "addr=10.0.0.5")
    assert manual_replay._device_args_for(config) == "addr=10.0.0.5"

    monkeypatch.setattr(settings, "x440_device_args", None)
    with pytest.raises(SystemExit):
        manual_replay._device_args_for(config)
