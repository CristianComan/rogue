"""Shared test fixtures — synthetic SigMF files only. CLAUDE.md's own
rule: tests never open a real radio, and no real recordings in the repo.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from sigmf import SigMFFile


def write_sigmf_tone(
    path_stem: Path,
    *,
    freq_offset_hz: float = 0.0,
    sample_rate_hz: float = 20_000.0,
    center_freq_hz: float = 2_440_000_000.0,
    duration_s: float = 1.0,
    amplitude: float = 0.5,
    experiment_scenario: str | None = None,
) -> Path:
    """Writes ``<path_stem>.sigmf-data``/``.sigmf-meta``: a pure tone at
    ``freq_offset_hz`` from the recording's own DC, ``cf32_le``. Returns
    the ``.sigmf-meta`` path. ``experiment_scenario``, when given, sets
    ``experiment:scenario`` (the field the real ROGUE drone corpus uses
    to mark air/los/nlos/controller/both) for `scan_rogue_corpus` tests.
    """
    path_stem.parent.mkdir(parents=True, exist_ok=True)
    n = round(duration_s * sample_rate_hz)
    t = np.arange(n) / sample_rate_hz
    samples = (amplitude * np.exp(2j * np.pi * freq_offset_hz * t)).astype(np.complex64)

    data_path = path_stem.with_name(path_stem.name + ".sigmf-data")
    meta_path = path_stem.with_name(path_stem.name + ".sigmf-meta")
    samples.tofile(data_path)

    global_info = {"core:datatype": "cf32_le", "core:sample_rate": sample_rate_hz}
    if experiment_scenario is not None:
        global_info["experiment:scenario"] = experiment_scenario
    meta = SigMFFile(data_file=str(data_path), global_info=global_info)
    meta.add_capture(0, metadata={"core:frequency": center_freq_hz})
    meta.tofile(meta_path, skip_validate=False)
    return meta_path
