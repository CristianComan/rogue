"""Compiler (CLAUDE.md build-order item 4): scenario + catalog -> one
composite SigMF file + report.json + spectrum.png + radio.json.

Per resolved event: read via the `sigmf` package (handles cf32_le/
ci16_le/ci8/cu8 -> complex64 automatically, "autoscale"), frequency-shift
at the recording's native rate, resample (`scipy.signal.resample_poly`)
to the radio's rate, cut/loop to the event's `dur_s`, apply `gain_db`,
place/sum into the composite. Then apply `noise_policy`, normalize to
`headroom_dbfs` peak (logging the scale factor into the report), and
write everything out.

Composite sizing follows CLAUDE.md's own worked example (duration x rate
x 8 bytes for cf32): past `ram_budget_gb` the composite buffer is a disk
`numpy.memmap` instead of an in-RAM array, so a long/high-rate composite
doesn't require loading it wholesale into memory (mirrors the main
ROGUE repo's own "bounded streaming buffers" rule, independently
applied here). Past `disk_budget_gb` compilation refuses outright unless
`allow_large=True`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # headless: this tool never needs an interactive plot window
import matplotlib.pyplot as plt
import numpy as np
from numpy.typing import NDArray
from scipy.signal import resample_poly
from sigmf import SigMFFile
from sigmf.sigmffile import fromfile

from replay_cli.schema import (
    Catalog,
    Event,
    NoisePolicy,
    Recording,
    ResolvedEvent,
    Scenario,
    resolve_events,
)
from replay_cli.validate import Issue, validate_scenario

BYTES_PER_SAMPLE_CF32 = 8
DEFAULT_DISK_BUDGET_GB = 100.0
DEFAULT_RAM_BUDGET_GB = 4.0

# Burst-gate heuristic (noise_policy: trim_bursts) — a simple windowed-RMS
# envelope threshold, not a sophisticated burst detector. Flagged as an
# assumption: CLAUDE.md's own "Open questions" leaves noise-policy
# behavior unresolved pending real recordings.
_GATE_WINDOW_S = 0.001
_GATE_THRESHOLD_DB = -40.0


class CompileError(Exception):
    """Raised for a hard-error condition (validation failure, budget
    exceeded, oversized composite) — never for a mere warning."""


@dataclass(frozen=True)
class CompileResult:
    out_dir: Path
    composite_meta_path: Path
    report_path: Path
    spectrum_png_path: Path
    radio_json_path: Path
    issues: list[Issue]


def compile_scenario(
    scenario_path: Path,
    catalog_path: Path,
    out_dir: Path,
    *,
    disk_budget_gb: float = DEFAULT_DISK_BUDGET_GB,
    ram_budget_gb: float = DEFAULT_RAM_BUDGET_GB,
    allow_large: bool = False,
) -> CompileResult:
    scenario = Scenario.load(scenario_path)
    catalog = Catalog.load(catalog_path)
    issues = validate_scenario(scenario, catalog)
    if any(issue.level == "error" for issue in issues):
        raise CompileError(f"scenario fails validation: {issues}")

    rate_hz = scenario.radio.rate_msps * 1e6
    total_samples = round(scenario.duration_s * rate_hz)
    composite_bytes = total_samples * BYTES_PER_SAMPLE_CF32
    disk_budget_bytes = disk_budget_gb * 1e9
    if composite_bytes > disk_budget_bytes and not allow_large:
        raise CompileError(
            f"composite would be {composite_bytes / 1e9:.1f} GB, exceeding the "
            f"{disk_budget_gb:.1f} GB disk budget (pass allow_large=True to override)"
        )

    scenario_out_dir = out_dir / scenario.name
    scenario_out_dir.mkdir(parents=True, exist_ok=True)
    data_path = scenario_out_dir / "composite.sigmf-data"
    meta_path = scenario_out_dir / "composite.sigmf-meta"

    ram_budget_bytes = ram_budget_gb * 1e9
    use_memmap = composite_bytes > ram_budget_bytes
    if use_memmap:
        issues.append(
            Issue(
                "warning",
                "compile",
                f"composite ({composite_bytes / 1e9:.1f} GB) exceeds the {ram_budget_gb:.1f} GB "
                "RAM budget; writing via memmap instead of an in-RAM buffer",
            )
        )
        composite: NDArray[np.complex64] | np.memmap = np.memmap(
            data_path, dtype=np.complex64, mode="w+", shape=(total_samples,)
        )
    else:
        composite = np.zeros(total_samples, dtype=np.complex64)

    resolved = resolve_events(scenario, catalog)
    for resolved_event, event in zip(resolved, scenario.events, strict=True):
        recording = resolved_event.recording
        if resolved_event.skipped or recording is None:
            continue
        placed = _process_event(event, recording, scenario, rate_hz, issues)
        start_sample = round(event.start_s * rate_hz)
        end_sample = min(start_sample + len(placed), total_samples)
        composite[start_sample:end_sample] += placed[: end_sample - start_sample]

    if scenario.noise_policy is NoisePolicy.TRIM_BURSTS:
        composite[:] = _gate_bursts(composite, rate_hz)

    peak = float(np.max(np.abs(composite))) if total_samples else 0.0
    scale = 1.0
    if peak > 0:
        target_peak = 10 ** (scenario.headroom_dbfs / 20)
        scale = target_peak / peak
        composite *= scale  # type: ignore[assignment]  # true in-place; numpy stubs model *= as out-of-place
    issues.append(Issue("warning", "compile", f"normalization scale factor applied: {scale:.6g}"))

    if use_memmap:
        composite.flush()  # type: ignore[union-attr]  # use_memmap True <=> composite is the np.memmap branch
    else:
        composite.tofile(data_path)

    sigmf_meta = SigMFFile(
        data_file=str(data_path),
        global_info={
            "core:datatype": "cf32_le",
            "core:sample_rate": rate_hz,
            "core:description": f"replay_cli composite for scenario {scenario.name!r}",
        },
    )
    sigmf_meta.add_capture(0, metadata={"core:frequency": scenario.radio.center_mhz * 1e6})
    sigmf_meta.tofile(meta_path, skip_validate=False)

    radio_json_path = scenario_out_dir / "radio.json"
    radio_json_path.write_text(json.dumps(scenario.radio.model_dump(mode="json"), indent=2))

    spectrum_png_path = scenario_out_dir / "spectrum.png"
    _write_spectrum_png(composite, rate_hz, spectrum_png_path)

    report_path = scenario_out_dir / "report.json"
    report_path.write_text(json.dumps(_build_report(scenario, resolved, scale, issues), indent=2))

    return CompileResult(
        out_dir=scenario_out_dir,
        composite_meta_path=meta_path,
        report_path=report_path,
        spectrum_png_path=spectrum_png_path,
        radio_json_path=radio_json_path,
        issues=issues,
    )


def _process_event(
    event: Event,
    recording: Recording,
    scenario: Scenario,
    rate_hz: float,
    issues: list[Issue],
) -> NDArray[np.complex64]:
    sig = fromfile(recording.meta, skip_checksum=True)
    samples = np.asarray(sig.read_samples()).astype(np.complex64)

    # validate_scenario (run before any of this in compile_scenario) already
    # rejects a recording with no known sample rate -- reaching here with
    # None would be a bug in that check, not a legitimate runtime case.
    orig_rate_hz = recording.sample_rate_hz
    if orig_rate_hz is None:
        raise CompileError(f"recording {recording.meta} has no known sample rate")

    if recording.center_freq_hz is not None:
        shift_hz = recording.center_freq_hz - scenario.radio.center_mhz * 1e6
        if shift_hz != 0:
            t = np.arange(samples.size, dtype=np.float64) / orig_rate_hz
            samples = (samples * np.exp(-2j * np.pi * shift_hz * t)).astype(np.complex64)

    if orig_rate_hz != rate_hz:
        frac = Fraction(round(rate_hz), round(orig_rate_hz)).limit_denominator(1000)
        samples = resample_poly(samples, frac.numerator, frac.denominator).astype(np.complex64)

    target_len = round(event.dur_s * rate_hz)
    if samples.size >= target_len:
        samples = samples[:target_len]
    elif event.loop:
        issues.append(
            Issue(
                "warning",
                f"event({event.drone})",
                "recording shorter than dur_s; looping introduces a seam discontinuity",
            )
        )
        samples = np.resize(samples, target_len)
    else:
        actual_s = samples.size / rate_hz
        issues.append(
            Issue(
                "warning",
                f"event({event.drone})",
                f"recording shorter than dur_s ({actual_s:.3f}s < {event.dur_s:.3f}s); "
                "remainder left silent",
            )
        )

    if event.gain_db:
        samples = (samples * (10 ** (event.gain_db / 20))).astype(np.complex64)
    return samples


def _gate_bursts(composite: NDArray[np.complex64], rate_hz: float) -> NDArray[np.complex64]:
    window = max(1, round(_GATE_WINDOW_S * rate_hz))
    power = np.abs(composite) ** 2
    kernel = np.ones(window, dtype=np.float64) / window
    envelope_power = np.convolve(power, kernel, mode="same")
    envelope_db = 10 * np.log10(np.maximum(envelope_power, 1e-20))
    peak_db = float(np.max(envelope_db)) if envelope_db.size else 0.0
    gate = envelope_db >= (peak_db + _GATE_THRESHOLD_DB)
    return np.where(gate, composite, np.complex64(0))


def _write_spectrum_png(composite: NDArray[np.complex64], rate_hz: float, out_path: Path) -> None:
    fig, ax = plt.subplots(figsize=(10, 4))
    if composite.size:
        # A fully (or partly) silent composite legitimately has a
        # zero-power bin somewhere -- log10(0) is expected, not a bug.
        with np.errstate(divide="ignore"):
            ax.specgram(composite, Fs=rate_hz)
    ax.set_xlabel("time (s)")
    ax.set_ylabel("frequency (Hz)")
    fig.tight_layout()
    fig.savefig(out_path)
    plt.close(fig)


def _build_report(
    scenario: Scenario, resolved: list[ResolvedEvent], scale: float, issues: list[Issue]
) -> dict[str, object]:
    events_report = []
    for resolved_event in resolved:
        event = resolved_event.event
        events_report.append(
            {
                "drone": event.drone,
                "variant": resolved_event.variant.value if resolved_event.variant else None,
                "reason": resolved_event.reason,
                "start_s": event.start_s,
                "end_s": event.end_s,
                "loop": event.loop,
                "skipped": resolved_event.skipped,
            }
        )
    return {
        "scenario": scenario.name,
        "radio": scenario.radio.type.value,
        "noise_policy": scenario.noise_policy.value,
        "headroom_dbfs": scenario.headroom_dbfs,
        "normalization_scale_factor": scale,
        "duration_s": scenario.duration_s,
        "events": events_report,
        "warnings": [
            {"level": issue.level, "where": issue.where, "message": issue.message}
            for issue in issues
        ],
    }
