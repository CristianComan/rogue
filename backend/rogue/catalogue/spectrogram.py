"""STFT-based spectrogram computation over raw SigMF I/Q sample bytes.

Pure and I/O-free, like ``sigmf.py``: takes already-fetched sample bytes — a
bounded time-window slice, never a full recording (see
``storage.object_store.get_object_range`` and ``api/recordings.py``'s
spectrogram endpoint) — and returns a compact time/frequency dB grid.
``numpy`` is already a project dependency; no new package is introduced.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

# Mirrors sigmf.py's _COMPONENT_BYTES keys, mapped to numpy component
# dtypes instead of byte counts. Kept separate from sigmf.py (rather than
# refactored to share one table) since sigmf.py's parsing is scoped to
# ingest/validation, not sample decoding.
_COMPONENT_DTYPE_CODES = {
    "f64": "f8",
    "f32": "f4",
    "i32": "i4",
    "u32": "u4",
    "i16": "i2",
    "u16": "u2",
    "i8": "i1",
    "u8": "u1",
}


def _numpy_dtype(sample_format: str) -> tuple[np.dtype, bool]:
    """(numpy component dtype, is_complex) for a SigMF ``core:datatype`` string."""
    body = sample_format
    if body.startswith("c"):
        is_complex = True
        body = body[1:]
    elif body.startswith("r"):
        is_complex = False
        body = body[1:]
    else:
        raise ValueError(f"unsupported sample_format {sample_format!r}")

    endian = "<"
    if body.endswith("_le"):
        body = body[:-3]
    elif body.endswith("_be"):
        endian = ">"
        body = body[:-3]

    code = _COMPONENT_DTYPE_CODES.get(body)
    if code is None:
        raise ValueError(f"unsupported sample_format {sample_format!r}")
    return np.dtype(endian + code), is_complex


def decode_iq_samples(raw: bytes, sample_format: str) -> np.ndarray:
    """Raw SigMF sample bytes -> a 1D complex128 array, baseband-normalized.

    Real (non-complex) formats decode with a zero imaginary part so callers
    have one uniform type. Integer formats are raw ADC codes, not
    normalized floats, so they're scaled by the dtype's max magnitude —
    float formats are assumed already scaled to roughly [-1, 1].
    """
    dtype, is_complex = _numpy_dtype(sample_format)
    values = np.frombuffer(raw, dtype=dtype)
    if is_complex:
        pairs = values[: len(values) - (len(values) % 2)].reshape(-1, 2)
        samples = pairs[:, 0].astype(np.float64) + 1j * pairs[:, 1].astype(np.float64)
    else:
        samples = values.astype(np.complex128)

    if np.issubdtype(dtype, np.integer):
        samples = samples / float(np.iinfo(dtype).max)
    return samples


@dataclass(frozen=True)
class SpectrogramResult:
    """A compact time/frequency dB grid: ``magnitude_db[time_bin][freq_bin]``."""

    time_offsets_s: list[float]
    freq_offsets_hz: list[float]
    magnitude_db: list[list[float]]


def compute_spectrogram(
    samples: np.ndarray, sample_rate_hz: float, fft_size: int = 1024
) -> SpectrogramResult:
    """Non-overlapping-window STFT of ``samples`` (complex128, baseband).

    A Hann window is applied per FFT block to limit spectral leakage.
    Frequency bins are centered (``fftshift``) around 0 Hz baseband — the
    caller re-centers on the link's live authored frequency for display,
    not this function.
    """
    if samples.size == 0:
        return SpectrogramResult(time_offsets_s=[], freq_offsets_hz=[], magnitude_db=[])

    effective_fft_size = min(fft_size, samples.size)
    n_windows = samples.size // effective_fft_size
    if n_windows == 0:
        return SpectrogramResult(time_offsets_s=[], freq_offsets_hz=[], magnitude_db=[])

    trimmed = samples[: n_windows * effective_fft_size].reshape(n_windows, effective_fft_size)
    window = np.hanning(effective_fft_size)
    spectra = np.fft.fftshift(np.fft.fft(trimmed * window, axis=1), axes=1)
    magnitude_db = 20 * np.log10(np.abs(spectra) + 1e-12)

    freq_offsets_hz = np.fft.fftshift(np.fft.fftfreq(effective_fft_size, d=1.0 / sample_rate_hz))
    time_offsets_s = (np.arange(n_windows) * effective_fft_size) / sample_rate_hz

    return SpectrogramResult(
        time_offsets_s=time_offsets_s.tolist(),
        freq_offsets_hz=freq_offsets_hz.tolist(),
        magnitude_db=magnitude_db.tolist(),
    )
