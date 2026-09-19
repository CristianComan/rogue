"""Tests for the Agent's local SigMF cache (M8, ADR-008) against a stubbed
object store — no real MinIO, matching CLAUDE.md §10's simulation default.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from uuid import uuid4

import pytest
from agents.common import cache

from rogue.protocol.messages import RecordingCacheEntry
from rogue.storage import object_store

META_BYTES = b'{"global": {}}'
DATA_BYTES = b"\x00\x01" * 1000


def _entry(**overrides: object) -> RecordingCacheEntry:
    kwargs: dict[str, object] = {
        "recording_id": uuid4(),
        "version": 1,
        "metadata_object_key": "recordings/demo.sigmf-meta",
        "data_object_key": "recordings/demo.sigmf-data",
        "sha256_metadata": hashlib.sha256(META_BYTES).hexdigest(),
        "sha256_data": hashlib.sha256(DATA_BYTES).hexdigest(),
    }
    kwargs.update(overrides)
    return RecordingCacheEntry(**kwargs)


@pytest.fixture(autouse=True)
def _stub_object_store(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(object_store, "get_object_bytes", lambda key: META_BYTES)

    def fake_stream(key: str, destination: Path) -> object_store.ObjectDigest:
        destination.write_bytes(DATA_BYTES)
        return object_store.ObjectDigest(
            sha256=hashlib.sha256(DATA_BYTES).hexdigest(),
            sha512=hashlib.sha512(DATA_BYTES).hexdigest(),
            size_bytes=len(DATA_BYTES),
        )

    monkeypatch.setattr(object_store, "stream_object_to_file", fake_stream)


async def test_ensure_cached_downloads_and_verifies(tmp_path: Path) -> None:
    entry = _entry()

    await cache.ensure_cached(tmp_path, entry)

    meta_path, data_path = cache._paths(tmp_path, entry)
    assert meta_path.read_bytes() == META_BYTES
    assert data_path.read_bytes() == DATA_BYTES


async def test_ensure_cached_skips_redownload_on_cache_hit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    entry = _entry()
    await cache.ensure_cached(tmp_path, entry)

    calls = []
    monkeypatch.setattr(
        object_store, "get_object_bytes", lambda key: calls.append(key) or META_BYTES
    )

    await cache.ensure_cached(tmp_path, entry)

    assert calls == []  # no re-download: the cached copy already matched the pinned hash


async def test_ensure_cached_raises_on_hash_mismatch(tmp_path: Path) -> None:
    entry = _entry(sha256_data="b" * 64)

    with pytest.raises(cache.CacheVerificationError):
        await cache.ensure_cached(tmp_path, entry)

    _, data_path = cache._paths(tmp_path, entry)
    assert not data_path.exists()
