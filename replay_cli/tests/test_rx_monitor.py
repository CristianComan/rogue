"""Tests for the RX waterfall monitor's pure logic and receiver loop
against a fake device seam — no real SoapySDR or hardware, no
matplotlib/plotting involved (CLAUDE.md rule 4).
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field

import numpy as np

from replay_cli.rx_monitor import ChannelWaterfall, receiver_loop

RATE_HZ = 2_000_000.0


def test_waterfall_scrolls_oldest_row_out() -> None:
    waterfall = ChannelWaterfall(fft_size=64, history=3, floor_db=-120.0)
    tone = (0.5 * np.exp(2j * np.pi * 0.1 * np.arange(64))).astype(np.complex64)

    waterfall.push(tone)

    assert waterfall.rows.shape == (3, 64)
    # The newest push always lands in the last row; older (still-floor)
    # rows are still at the floor until pushed into.
    assert np.all(waterfall.rows[0] == -120.0)
    assert np.all(waterfall.rows[1] == -120.0)
    assert np.max(waterfall.rows[-1]) > -120.0


def test_waterfall_tracks_three_pushes_in_order() -> None:
    waterfall = ChannelWaterfall(fft_size=64, history=2, floor_db=-120.0)
    silence = np.zeros(64, dtype=np.complex64)
    tone = (0.9 * np.exp(2j * np.pi * 0.1 * np.arange(64))).astype(np.complex64)

    waterfall.push(silence)
    waterfall.push(tone)

    # silence pushed first should have scrolled to row 0, tone to row -1.
    assert np.max(waterfall.rows[0]) < np.max(waterfall.rows[-1])


@dataclass
class _FakeRxDevice:
    configured: dict[int, dict[str, float]] = field(default_factory=dict)
    opened_streams: list[int] = field(default_factory=list)
    closed_streams: list[object] = field(default_factory=list)
    chunks_to_deliver: int = 5

    def configure(self, channel: int, *, freq_hz: float, rate_hz: float, gain_db: float) -> None:
        self.configured[channel] = {"freq_hz": freq_hz, "rate_hz": rate_hz, "gain_db": gain_db}

    def open_stream(self, channel: int) -> object:
        self.opened_streams.append(channel)
        return {"channel": channel, "reads": 0}

    def read(self, stream: object, buf: np.ndarray) -> int:
        assert isinstance(stream, dict)
        stream["reads"] += 1
        buf[:] = 0.3 * np.exp(2j * np.pi * 0.2 * np.arange(len(buf)))
        return len(buf) if stream["reads"] <= self.chunks_to_deliver else 0

    def close_stream(self, stream: object) -> None:
        self.closed_streams.append(stream)


def test_receiver_loop_pushes_into_waterfall_and_closes_stream_on_stop() -> None:
    device = _FakeRxDevice(chunks_to_deliver=1000)
    waterfall = ChannelWaterfall(fft_size=64, history=4)
    stop = threading.Event()

    thread = threading.Thread(
        target=receiver_loop,
        args=(device, 2),
        kwargs={
            "freq_hz": 2.45e9,
            "rate_hz": RATE_HZ,
            "gain_db": -5.0,
            "chunk_samples": 64,
            "waterfall": waterfall,
            "stop": stop,
        },
    )
    thread.start()
    stop.set()
    thread.join(timeout=5)

    assert not thread.is_alive()
    assert device.configured[2] == {"freq_hz": 2.45e9, "rate_hz": RATE_HZ, "gain_db": -5.0}
    assert device.opened_streams == [2]
    assert len(device.closed_streams) == 1
