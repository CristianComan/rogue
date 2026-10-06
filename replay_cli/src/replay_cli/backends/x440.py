"""Ettus X440 playback backend — **not implemented** (CLAUDE.md build-order
item 6, deferred: the user's stated priority is AIR-T 7311 then AIR-T
7201 before X440).

Per the doc, this should prefer UHD's RFNoC Replay block (gap-free
streaming from DRAM) via the UHD Python API, falling back to shelling
out to `rfnoc_replay_samples_from_file` / `tx_samples_from_file`, with
flags verified against the installed UHD version's `--help`. None of
that is implemented here — this module only exists so `cli.py` can
import `X440Backend` and fail with a clear, specific error rather than
an `ImportError`/`AttributeError` if `--radio x440` is selected.
"""

from __future__ import annotations

from pathlib import Path


class X440Backend:
    def __init__(self, device_args: str, channel: int) -> None:
        self._device_args = device_args
        self._channel = channel

    def play(self, composite_meta: Path, gain_db: float, repeat: int, arm: bool) -> None:
        raise NotImplementedError(
            "X440 playback is not implemented yet (CLAUDE.md build-order item 6) — "
            "AIR-T 7311/7201 are the current priority. See backends/x440.py's docstring "
            "for what's needed (RFNoC Replay block via the UHD Python API)."
        )
