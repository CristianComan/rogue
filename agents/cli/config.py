"""YAML config and local-recording staging for the manual replay CLI (M19,
ADR-019).

The manual replay CLI is deliberately backend-free: no Postgres catalogue,
no MinIO, no NATS. A recording is just a local ``.sigmf-data``/``.sigmf-
meta`` pair on the Agent host. `stage_local_recording` makes that pair
visible to the real, unmodified `StreamingSDRAdapter.preflight()`
(agents/common/sdr_adapter_base.py), which only knows how to find bytes via
`agents.common.cache.data_path_for`/`meta_path_for`'s naming convention —
by symlinking rather than copying, so a run never duplicates a
potentially large recording (CLAUDE.md rule 8) or touches the source file
(CLAUDE.md rule 7).
"""

from __future__ import annotations

import hashlib
import uuid
from pathlib import Path
from typing import Literal

import yaml
from pydantic import Field, field_validator

from agents.common import cache
from rogue.catalogue.sigmf import bytes_per_sample, parse_metadata
from rogue.domain.common import RogueModel
from rogue.domain.recording import AccessClassification, IQRecording

# Fixed, arbitrary namespace UUID so the same local file path always
# derives the same recording id across separate CLI invocations — that's
# what makes staging idempotent (a re-run reuses the existing symlink
# instead of raising on a name collision).
_LOCAL_RECORDING_NAMESPACE = uuid.UUID("6f2c9b1e-6e0a-4c7a-9d3e-2b7a6c4f8a10")
_LOCAL_RECORDING_VERSION = 1


class RecordingSpec(RogueModel):
    """One local recording to stream, and its relative (digital) gain.

    ``gain_offset_db`` is applied in software to the I/Q samples before
    they reach the device (``CompositeChannel.gain_offset_db``,
    ``StreamingSDRAdapter._stream``) — the real device's own analog TX
    gain stays at the adapter's fixed default (see
    ``agents/common/sdr_adapter_base.py``'s ``DEFAULT_GAIN_DB``; a real
    gain policy is a pre-existing, documented gap unchanged since M9, not
    something M19 introduces or fixes).
    """

    path: Path
    gain_offset_db: float = 0.0

    @field_validator("path")
    @classmethod
    def _resolve(cls, value: Path) -> Path:
        return value.expanduser().resolve()


class ManualReplayConfig(RogueModel):
    """One physical channel's worth of manual-replay configuration."""

    device_family: Literal["x440", "air7311"]
    # SoapySDR-native Deepwave AIR-T units beyond the AIR7311 (AIR7201,
    # AIR8201, ...) are driven through this same "air7311" family — they
    # differ only in their SoapySDR driver string, carried in device_args.
    device_args: str | None = None
    device_id: str = "manual-1"
    channel_index: int = Field(ge=0)
    center_frequency_hz: float = Field(gt=0)
    bandwidth_hz: float = Field(gt=0)
    recordings: list[RecordingSpec] = Field(min_length=1)
    lease_ttl_seconds: float = 300.0
    cache_dir: Path = Field(default_factory=lambda: Path.home() / ".cache" / "rogue-manual-replay")

    @field_validator("cache_dir")
    @classmethod
    def _resolve_cache_dir(cls, value: Path) -> Path:
        return value.expanduser().resolve()


def load_config(path: Path) -> ManualReplayConfig:
    raw = yaml.safe_load(path.read_text())
    return ManualReplayConfig.model_validate(raw or {})


def _sha256_of_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def stage_local_recording(cache_dir: Path, source_data_path: Path) -> IQRecording:
    """Make one local ``.sigmf-data`` file (with a sibling ``.sigmf-meta``)
    readable by `StreamingSDRAdapter.preflight()` and build the
    `IQRecording` it needs to pair against a `CompositeChannel`.

    Symlinks rather than copies (never modifies or duplicates the source);
    a repeat call against the same path is a no-op past the first symlink.
    """
    if source_data_path.suffix != ".sigmf-data":
        raise ValueError(f"{source_data_path} is not a .sigmf-data file")
    if not source_data_path.is_file():
        raise FileNotFoundError(source_data_path)
    source_meta_path = source_data_path.with_name(
        source_data_path.name[: -len(".sigmf-data")] + ".sigmf-meta"
    )
    if not source_meta_path.is_file():
        raise FileNotFoundError(source_meta_path)

    recording_id = uuid.uuid5(_LOCAL_RECORDING_NAMESPACE, str(source_data_path))
    version = _LOCAL_RECORDING_VERSION
    cache_dir.mkdir(parents=True, exist_ok=True)
    staged_data_path = cache.data_path_for(cache_dir, recording_id, version)
    staged_meta_path = cache.meta_path_for(cache_dir, recording_id, version)
    if not staged_data_path.exists():
        staged_data_path.symlink_to(source_data_path)
    if not staged_meta_path.exists():
        staged_meta_path.symlink_to(source_meta_path)

    parsed = parse_metadata(source_meta_path.read_bytes())
    if parsed.errors or parsed.sample_rate_hz is None:
        raise ValueError(f"{source_meta_path}: invalid SigMF metadata: {parsed.errors}")
    sample_size = bytes_per_sample(parsed.sample_format)
    if sample_size is None:
        raise ValueError(f"{source_meta_path}: unsupported core:datatype {parsed.sample_format!r}")
    sample_count = source_data_path.stat().st_size // sample_size

    return IQRecording(
        id=recording_id,
        version=version,
        # Not real object-store keys (there is no catalogue here) — kept
        # as the local source path for traceability in status/logs.
        metadata_object_key=str(source_meta_path),
        data_object_key=str(source_data_path),
        sha256_metadata=_sha256_of_file(source_meta_path),
        sha256_data=_sha256_of_file(source_data_path),
        sample_format=parsed.sample_format,
        sample_rate_hz=parsed.sample_rate_hz,
        sample_count=sample_count,
        duration_s=sample_count / parsed.sample_rate_hz,
        center_frequency_hz=parsed.center_frequency_hz,
        access_classification=AccessClassification.RESTRICTED,
    )
