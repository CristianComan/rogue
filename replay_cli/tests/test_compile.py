from pathlib import Path

import numpy as np
import pytest
import yaml
from sigmf.sigmffile import fromfile

from conftest import write_sigmf_tone
from replay_cli.catalog_scan import scan_recordings, write_catalog
from replay_cli.compile import CompileError, compile_scenario

# Keep the radio's rate equal to the synthetic recordings' own rate
# (20 kHz) throughout this file -- these tests care about frequency
# shift/loop/truncate/normalize correctness, not resampling, and a 1:1
# ratio avoids an accidental 1000x upsample (rate_msps is nominally
# "megasamples/sec", but nothing stops a tiny unitless value here).
RATE_HZ = 20_000.0
RATE_MSPS = RATE_HZ / 1e6
CENTER_MHZ = 2440.0


def _write_scenario_and_catalog(
    tmp_path: Path,
    rec_dir: Path,
    *,
    dur_s: float = 1.0,
    loop: bool = False,
    noise_policy: str = "keep",
    headroom_dbfs: float = -3.0,
    gain_db: float = 0.0,
    rate_msps: float = RATE_MSPS,
) -> tuple[Path, Path]:
    # Builds the catalog the real way (scan_recordings), so every
    # Recording field the validator/compiler reads (datatype, sample
    # rate, center frequency, duration) is genuinely populated, not
    # hand-typed — these tests exercise the actual scan -> validate ->
    # compile pipeline, not a shortcut around it.
    catalog_path = tmp_path / "catalog.yaml"
    write_catalog(scan_recordings(rec_dir).catalog, catalog_path)
    scenario_path = tmp_path / "scenario.yaml"
    scenario_path.write_text(
        yaml.safe_dump(
            {
                "name": "t",
                "radio": {
                    "type": "airt7311",
                    "channel": 0,
                    "center_mhz": CENTER_MHZ,
                    "rate_msps": rate_msps,
                    "tx_gain_db": -10,
                    "max_tx_gain_db": -5,
                },
                "events": [
                    {
                        "drone": "alpha",
                        "near": ["drone"],
                        "start_s": 0.0,
                        "dur_s": dur_s,
                        "loop": loop,
                        "gain_db": gain_db,
                    }
                ],
                "noise_policy": noise_policy,
                "headroom_dbfs": headroom_dbfs,
            }
        )
    )
    return scenario_path, catalog_path


def test_compile_writes_all_output_files(tmp_path: Path) -> None:
    write_sigmf_tone(
        tmp_path / "rec" / "alpha" / "drone",
        sample_rate_hz=RATE_HZ,
        center_freq_hz=CENTER_MHZ * 1e6,
        duration_s=1.0,
    )
    scenario_path, catalog_path = _write_scenario_and_catalog(tmp_path, tmp_path / "rec")

    result = compile_scenario(scenario_path, catalog_path, tmp_path / "out")

    assert result.composite_meta_path.is_file()
    assert result.composite_meta_path.with_name("composite.sigmf-data").is_file()
    assert result.report_path.is_file()
    assert result.spectrum_png_path.is_file()
    assert result.radio_json_path.is_file()


def test_compile_rejects_an_invalid_scenario(tmp_path: Path) -> None:
    # 5.8 GHz away from the 2440 MHz radio center -> fails the
    # usable-bandwidth fit check in validate_scenario.
    write_sigmf_tone(
        tmp_path / "rec" / "alpha" / "drone", sample_rate_hz=RATE_HZ, center_freq_hz=5_800e6
    )
    scenario_path, catalog_path = _write_scenario_and_catalog(tmp_path, tmp_path / "rec")

    with pytest.raises(CompileError):
        compile_scenario(scenario_path, catalog_path, tmp_path / "out")


def test_compile_refuses_past_disk_budget(tmp_path: Path) -> None:
    write_sigmf_tone(
        tmp_path / "rec" / "alpha" / "drone",
        sample_rate_hz=RATE_HZ,
        center_freq_hz=CENTER_MHZ * 1e6,
    )
    scenario_path, catalog_path = _write_scenario_and_catalog(tmp_path, tmp_path / "rec")

    with pytest.raises(CompileError):
        compile_scenario(scenario_path, catalog_path, tmp_path / "out", disk_budget_gb=1e-9)


def test_compile_applies_frequency_shift(tmp_path: Path) -> None:
    # A pure-DC (0 Hz baseband) recording captured 5 kHz above the
    # radio's center -> after the compiler's shift (applied at the
    # recording's own 20 kHz native rate, safely under its 10 kHz
    # Nyquist), its tone must land at exactly -5 kHz baseband (one exact
    # cycle count over 1 second, so the FFT bin is exact, no leakage).
    # A generous radio rate (100 kHz) keeps the fit check's conservative
    # span (shift +/- the recording's own sample rate/2) comfortably
    # inside the usable bandwidth, and exercises the resample step too.
    shift_hz = 5_000.0
    out_rate_hz = 100_000.0
    write_sigmf_tone(
        tmp_path / "rec" / "alpha" / "drone",
        freq_offset_hz=0.0,
        sample_rate_hz=RATE_HZ,
        center_freq_hz=CENTER_MHZ * 1e6 + shift_hz,
        duration_s=1.0,
    )
    scenario_path, catalog_path = _write_scenario_and_catalog(
        tmp_path, tmp_path / "rec", headroom_dbfs=0.0, rate_msps=out_rate_hz / 1e6
    )

    result = compile_scenario(scenario_path, catalog_path, tmp_path / "out")

    composite = fromfile(result.composite_meta_path, skip_checksum=True).read_samples()
    spectrum = np.fft.fftshift(np.fft.fft(composite))
    freqs = np.fft.fftshift(np.fft.fftfreq(len(composite), d=1 / out_rate_hz))
    peak_freq = freqs[np.argmax(np.abs(spectrum))]
    assert peak_freq == pytest.approx(-shift_hz, abs=1.0)


def test_compile_pads_silently_when_shorter_and_not_looping(tmp_path: Path) -> None:
    write_sigmf_tone(
        tmp_path / "rec" / "alpha" / "drone",
        sample_rate_hz=RATE_HZ,
        center_freq_hz=CENTER_MHZ * 1e6,
        duration_s=0.5,
        amplitude=0.9,
    )
    scenario_path, catalog_path = _write_scenario_and_catalog(
        tmp_path, tmp_path / "rec", dur_s=1.0, loop=False, headroom_dbfs=0.0
    )

    result = compile_scenario(scenario_path, catalog_path, tmp_path / "out")

    composite = fromfile(result.composite_meta_path, skip_checksum=True).read_samples()
    tail = composite[round(0.6 * RATE_HZ) :]
    assert np.allclose(tail, 0.0)


def test_compile_loops_when_shorter_and_looping(tmp_path: Path) -> None:
    write_sigmf_tone(
        tmp_path / "rec" / "alpha" / "drone",
        sample_rate_hz=RATE_HZ,
        center_freq_hz=CENTER_MHZ * 1e6,
        duration_s=0.5,
        amplitude=0.9,
    )
    scenario_path, catalog_path = _write_scenario_and_catalog(
        tmp_path, tmp_path / "rec", dur_s=1.0, loop=True, headroom_dbfs=0.0
    )

    result = compile_scenario(scenario_path, catalog_path, tmp_path / "out")

    composite = fromfile(result.composite_meta_path, skip_checksum=True).read_samples()
    tail = composite[round(0.6 * RATE_HZ) :]
    assert not np.allclose(tail, 0.0)
    assert any(
        issue.message.startswith("recording shorter than dur_s; looping") for issue in result.issues
    )


def test_compile_normalizes_to_headroom(tmp_path: Path) -> None:
    write_sigmf_tone(
        tmp_path / "rec" / "alpha" / "drone",
        sample_rate_hz=RATE_HZ,
        center_freq_hz=CENTER_MHZ * 1e6,
        duration_s=1.0,
        amplitude=0.1,
    )
    scenario_path, catalog_path = _write_scenario_and_catalog(
        tmp_path, tmp_path / "rec", headroom_dbfs=-6.0
    )

    result = compile_scenario(scenario_path, catalog_path, tmp_path / "out")

    composite = fromfile(result.composite_meta_path, skip_checksum=True).read_samples()
    peak = float(np.max(np.abs(composite)))
    assert peak == pytest.approx(10 ** (-6.0 / 20), rel=1e-3)
