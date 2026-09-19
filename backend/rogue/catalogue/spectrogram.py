"""STFT-based spectrogram computation over raw SigMF I/Q sample bytes.

Pure and I/O-free, like ``sigmf.py``: takes already-fetched sample bytes,
never touches object storage itself (``catalogue/ingest.py`` does the
fetching via ``storage.object_store``). ``numpy`` is already a project
dependency; no new package is introduced.

Computed once at ingest as a coarse whole-recording overview
(``compute_overview_spectrogram``), not live per playback request. A first
version computed a live STFT per request over a bounded time window; at a
real drone-corpus sample rate (20 Msps in this repo's own test fixtures), a
2-second scrub window alone decodes to ~640 MB, which is too expensive to
compute synchronously on demand — especially with several Waterfall panels
open during multi-drone playback. The overview instead sparsely samples a
small, fixed number of short FFT windows spread across the whole recording
(a few MB of bounded reads total, regardless of the recording's real
length) and is stored once on ``IQRecording.overview_spectrogram``.
"""

from __future__ import annotations

import numpy as np

from rogue.domain.recording import SpectrogramOverview

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


def compute_spectrogram(
    samples: np.ndarray, sample_rate_hz: float, fft_size: int = 1024
) -> SpectrogramOverview:
    """Non-overlapping-window STFT of ``samples`` (complex128, baseband).

    A Hann window is applied per FFT block to limit spectral leakage.
    Frequency bins are centered (``fftshift``) around 0 Hz baseband — the
    caller re-centers on the link's live authored frequency for display,
    not this function.
    """
    if samples.size == 0:
        return SpectrogramOverview(time_offsets_s=[], freq_offsets_hz=[], magnitude_db=[])

    effective_fft_size = min(fft_size, samples.size)
    n_windows = samples.size // effective_fft_size
    if n_windows == 0:
        return SpectrogramOverview(time_offsets_s=[], freq_offsets_hz=[], magnitude_db=[])

    trimmed = samples[: n_windows * effective_fft_size].reshape(n_windows, effective_fft_size)
    window = np.hanning(effective_fft_size)
    spectra = np.fft.fftshift(np.fft.fft(trimmed * window, axis=1), axes=1)
    magnitude_db = 20 * np.log10(np.abs(spectra) + 1e-12)

    freq_offsets_hz = np.fft.fftshift(np.fft.fftfreq(effective_fft_size, d=1.0 / sample_rate_hz))
    time_offsets_s = (np.arange(n_windows) * effective_fft_size) / sample_rate_hz

    return SpectrogramOverview(
        time_offsets_s=time_offsets_s.tolist(),
        freq_offsets_hz=freq_offsets_hz.tolist(),
        magnitude_db=magnitude_db.tolist(),
    )


def compute_overview_spectrogram(
    chunks: list[bytes],
    time_offsets_s: list[float],
    sample_format: str,
    sample_rate_hz: float,
    fft_size: int = 256,
) -> SpectrogramOverview:
    """Assemble a whole-recording overview from independently fetched chunks.

    Each element of ``chunks`` is exactly ``fft_size`` samples' worth of raw
    bytes, fetched by the caller (``catalogue/ingest.py``) via bounded,
    independent range-reads spread across the recording — this function does
    no I/O itself. One FFT window per chunk; ``time_offsets_s`` (parallel to
    ``chunks``) becomes the overview's time axis as given, since it reflects
    where in the *original* recording each chunk was read from, not
    positions relative to this smaller working set.
    """
    if not chunks:
        return SpectrogramOverview(time_offsets_s=[], freq_offsets_hz=[], magnitude_db=[])

    magnitude_rows: list[list[float]] = []
    freq_offsets_hz: list[float] = []
    for chunk in chunks:
        samples = decode_iq_samples(chunk, sample_format)
        result = compute_spectrogram(samples, sample_rate_hz, fft_size=fft_size)
        if result.magnitude_db:
            magnitude_rows.append(result.magnitude_db[0])
            freq_offsets_hz = result.freq_offsets_hz
        else:
            magnitude_rows.append([])

    return SpectrogramOverview(
        time_offsets_s=time_offsets_s, freq_offsets_hz=freq_offsets_hz, magnitude_db=magnitude_rows
    )
