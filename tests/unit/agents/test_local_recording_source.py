"""Tests for the local-SigMF-root recording source (ADR-019, M19b): a
hash-verified recording under a configured local root must become readable
through `cache.py`'s own `meta_path_for`/`data_path_for(cache_dir, ...)` —
the exact contract `agent.py`'s `_load_cached_recording` depends on,
regardless of which source populated `cache_dir`.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from uuid import uuid4

import pytest
from agents.common import cache, local_recording_source

from rogue.protocol.messages import RecordingCacheEntry

RECORDING_ID = uuid4()
VERSION = 1
META_BYTES = b'{"global": {"core:datatype": "cf32_le", "core:sample_rate": 1000000}}'
DATA_BYTES = b"\x00" * 8 * 10


def _entry(sha256_data: str) -> RecordingCacheEntry:
    return RecordingCacheEntry(
        recording_id=RECORDING_ID,
        version=VERSION,
        metadata_object_key="unused-in-local-mode.sigmf-meta",
        data_object_key="unused-in-local-mode.sigmf-data",
        sha256_metadata="a" * 64,
        sha256_data=sha256_data,
    )


def _write_local_recording(local_root: Path, data: bytes = DATA_BYTES) -> None:
    local_root.mkdir(parents=True, exist_ok=True)
    (local_root / f"{RECORDING_ID}.v{VERSION}.sigmf-meta").write_bytes(META_BYTES)
    (local_root / f"{RECORDING_ID}.v{VERSION}.sigmf-data").write_bytes(data)


async def test_ensure_cached_symlinks_a_verified_pair_into_cache_dir(tmp_path: Path) -> None:
    local_root = tmp_path / "local-root"
    cache_dir = tmp_path / "cache"
    _write_local_recording(local_root)
    entry = _entry(hashlib.sha256(DATA_BYTES).hexdigest())

    await local_recording_source.ensure_cached(local_root, cache_dir, entry)

    meta_path = cache.meta_path_for(cache_dir, RECORDING_ID, VERSION)
    data_path = cache.data_path_for(cache_dir, RECORDING_ID, VERSION)
    assert meta_path.read_bytes() == META_BYTES
    assert data_path.read_bytes() == DATA_BYTES


async def test_ensure_cached_rejects_a_hash_mismatch(tmp_path: Path) -> None:
    local_root = tmp_path / "local-root"
    cache_dir = tmp_path / "cache"
    _write_local_recording(local_root)
    entry = _entry("f" * 64)  # wrong pinned hash

    with pytest.raises(cache.CacheVerificationError, match="does not match"):
        await local_recording_source.ensure_cached(local_root, cache_dir, entry)


async def test_ensure_cached_rejects_a_missing_pair(tmp_path: Path) -> None:
    local_root = tmp_path / "local-root"
    local_root.mkdir()
    cache_dir = tmp_path / "cache"
    entry = _entry(hashlib.sha256(DATA_BYTES).hexdigest())

    with pytest.raises(cache.CacheVerificationError, match="not found"):
        await local_recording_source.ensure_cached(local_root, cache_dir, entry)


async def test_ensure_cached_rejects_path_traversal_via_recording_id(tmp_path: Path) -> None:
    # A crafted RecordingCacheEntry can't actually carry ".." in a UUID field,
    # but a symlink placed under local_root pointing outside it must still be
    # rejected — this is the realistic escape vector for a filesystem-backed
    # source (the MinIO path has no equivalent, since object keys aren't paths).
    local_root = tmp_path / "local-root"
    local_root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.sigmf-meta").write_bytes(META_BYTES)
    (outside / "secret.sigmf-data").write_bytes(DATA_BYTES)
    (local_root / f"{RECORDING_ID}.v{VERSION}.sigmf-meta").symlink_to(outside / "secret.sigmf-meta")
    (local_root / f"{RECORDING_ID}.v{VERSION}.sigmf-data").symlink_to(outside / "secret.sigmf-data")
    cache_dir = tmp_path / "cache"
    entry = _entry(hashlib.sha256(DATA_BYTES).hexdigest())

    with pytest.raises(cache.CacheVerificationError, match="outside the configured local"):
        await local_recording_source.ensure_cached(local_root, cache_dir, entry)
