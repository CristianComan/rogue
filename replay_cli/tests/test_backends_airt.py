"""Tests for AIRTBackend against a fake SoapySDR-shaped device — no real
SoapySDR or hardware (CLAUDE.md rule 4). Confirms the safety rules
(dry-run default, typed confirmation, no bypass flag) and that the
stream is always closed, even on a mid-write failure.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pytest

from conftest import write_sigmf_tone
from replay_cli.backends.airt import AIRTBackend, play_on_channels

CHANNEL = 0


@dataclass
class _FakeSoapyDevice:
    configured: dict[int, dict[str, float]] = field(default_factory=dict)
    written_chunks: dict[int, list[np.ndarray]] = field(default_factory=dict)
    closed: list[int] = field(default_factory=list)
    master_clock_rates: list[float] = field(default_factory=list)
    fail_on_write: bool = False

    def set_master_clock_rate(self, rate_hz: float) -> None:
        self.master_clock_rates.append(rate_hz)

    def configure(self, channel: int, *, freq_hz: float, rate_hz: float, gain_db: float) -> None:
        self.configured[channel] = {"freq_hz": freq_hz, "rate_hz": rate_hz, "gain_db": gain_db}

    def write(self, channel: int, iq_cs16_interleaved: np.ndarray) -> None:
        if self.fail_on_write:
            raise RuntimeError("simulated write failure")
        self.written_chunks.setdefault(channel, []).append(iq_cs16_interleaved)

    def close(self, channel: int) -> None:
        self.closed.append(channel)


def _composite(tmp_path: Path, duration_s: float = 0.1) -> Path:
    return write_sigmf_tone(
        tmp_path / "composite",
        sample_rate_hz=20_000.0,
        center_freq_hz=2_440e6,
        duration_s=duration_s,
    )


def test_dry_run_never_touches_the_device_or_asks_for_confirmation(tmp_path: Path) -> None:
    composite = _composite(tmp_path)
    device = _FakeSoapyDevice()
    confirm_calls: list[str] = []
    backend = AIRTBackend(
        "driver=SoapyAIRT",
        CHANNEL,
        device=device,
        confirm=lambda p: confirm_calls.append(p) or "yes",
    )

    backend.play(composite, gain_db=10.0, repeat=1, arm=False)

    assert device.configured == {}
    assert device.written_chunks == {}
    assert confirm_calls == []


def test_arm_without_typed_yes_does_not_transmit(tmp_path: Path) -> None:
    composite = _composite(tmp_path)
    device = _FakeSoapyDevice()
    backend = AIRTBackend("driver=SoapyAIRT", CHANNEL, device=device, confirm=lambda p: "no")

    backend.play(composite, gain_db=10.0, repeat=1, arm=True)

    assert device.configured == {}
    assert device.closed == []


def test_arm_with_typed_yes_configures_transmits_and_closes(tmp_path: Path) -> None:
    composite = _composite(tmp_path)
    device = _FakeSoapyDevice()
    backend = AIRTBackend("driver=SoapyAIRT", CHANNEL, device=device, confirm=lambda p: "yes")

    backend.play(composite, gain_db=12.5, repeat=2, arm=True)

    assert device.configured[CHANNEL]["gain_db"] == 12.5
    assert device.configured[CHANNEL]["freq_hz"] == 2_440e6
    assert len(device.written_chunks[CHANNEL]) == 2  # repeat=2, in-RAM path -> one write per repeat
    assert device.closed == [CHANNEL]
    # Real AIR7311 hardware refuses setSampleRate() unless the master
    # clock rate was already set to match -- must happen before configure().
    assert device.master_clock_rates == [20_000.0]


def test_stream_is_closed_even_if_a_write_fails(tmp_path: Path) -> None:
    composite = _composite(tmp_path)
    device = _FakeSoapyDevice(fail_on_write=True)
    backend = AIRTBackend("driver=SoapyAIRT", CHANNEL, device=device, confirm=lambda p: "yes")

    with pytest.raises(RuntimeError):
        backend.play(composite, gain_db=0.0, repeat=1, arm=True)

    assert device.closed == [CHANNEL]


def test_composite_past_ram_budget_streams_in_chunks(tmp_path: Path) -> None:
    composite = _composite(tmp_path, duration_s=1.0)
    device = _FakeSoapyDevice()
    # An absurdly small RAM budget forces the chunked/prefetch-thread
    # path even for this small test file.
    backend = AIRTBackend(
        "driver=SoapyAIRT", CHANNEL, device=device, ram_budget_gb=1e-12, confirm=lambda p: "yes"
    )

    backend.play(composite, gain_db=0.0, repeat=1, arm=True)

    assert len(device.written_chunks[CHANNEL]) >= 1
    assert device.closed == [CHANNEL]


def test_multi_channel_dry_run_never_touches_device(tmp_path: Path) -> None:
    composite = _composite(tmp_path)
    device = _FakeSoapyDevice()

    play_on_channels(
        "driver=SoapyAIRT",
        [0, 1, 2, 3],
        composite,
        gain_db=10.0,
        repeat=1,
        arm=False,
        device=device,
    )

    assert device.configured == {}
    assert device.written_chunks == {}


def test_multi_channel_arm_without_typed_yes_does_not_transmit(tmp_path: Path) -> None:
    composite = _composite(tmp_path)
    device = _FakeSoapyDevice()

    play_on_channels(
        "driver=SoapyAIRT",
        [0, 1, 2, 3],
        composite,
        gain_db=10.0,
        repeat=1,
        arm=True,
        device=device,
        confirm=lambda p: "no",
    )

    assert device.configured == {}
    assert device.closed == []


def test_multi_channel_transmits_on_every_channel_with_attenuation_applied(tmp_path: Path) -> None:
    composite = _composite(tmp_path)
    device = _FakeSoapyDevice()

    play_on_channels(
        "driver=SoapyAIRT",
        [0, 1, 2, 3],
        composite,
        gain_db=10.0,
        repeat=1,
        arm=True,
        tx_attenuation_db=25.0,
        device=device,
        confirm=lambda p: "yes",
    )

    assert set(device.configured) == {0, 1, 2, 3}
    for channel in (0, 1, 2, 3):
        assert device.configured[channel]["gain_db"] == -15.0  # 10 - 25
        assert len(device.written_chunks[channel]) == 1
    assert sorted(device.closed) == [0, 1, 2, 3]
    # Set once for the whole device, before any per-channel configure --
    # not once per channel (changing it with an active stream on another
    # channel isn't supported on real hardware).
    assert device.master_clock_rates == [20_000.0]


def test_multi_channel_closes_every_channel_even_if_one_fails(tmp_path: Path) -> None:
    composite = _composite(tmp_path)
    device = _FakeSoapyDevice(fail_on_write=True)

    with pytest.raises(RuntimeError, match="channel"):
        play_on_channels(
            "driver=SoapyAIRT",
            [0, 1, 2, 3],
            composite,
            gain_db=0.0,
            repeat=1,
            arm=True,
            device=device,
            confirm=lambda p: "yes",
        )

    assert sorted(device.closed) == [0, 1, 2, 3]
