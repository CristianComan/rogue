"""Catalogue persistence tests against a real Postgres (see conftest.py).

Ingest goes through ``rogue.persistence.catalogue.ingest_recording``, which
calls ``rogue.catalogue.ingest.build_ingest_candidate`` — that function's own
object-storage calls are monkeypatched here too, so these tests need
Postgres but not a real MinIO, matching CLAUDE.md's simulation-by-default
testing rule.
"""

from __future__ import annotations

import hashlib
import json
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from rogue.domain.recording import AccessClassification
from rogue.persistence import catalogue, repository
from rogue.storage import object_store
from rogue.storage.object_store import ObjectDigest

METADATA_KEY = "recordings/example.sigmf-meta"
DATA_KEY = "recordings/example.sigmf-data"
DATA_BYTES = b"\x00" * 800  # 100 cf32 samples


def _metadata_bytes() -> bytes:
    document = {
        "global": {"core:datatype": "cf32_le", "core:sample_rate": 1_000_000.0},
        "captures": [{"core:frequency": 2_450_000_000.0}],
    }
    return json.dumps(document).encode()


@pytest.fixture(autouse=True)
def _valid_object_store(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(object_store, "get_object_bytes", lambda key: _metadata_bytes())
    monkeypatch.setattr(
        object_store,
        "digest_object",
        lambda key: ObjectDigest(
            sha256=hashlib.sha256(DATA_BYTES).hexdigest(),
            sha512=hashlib.sha512(DATA_BYTES).hexdigest(),
            size_bytes=len(DATA_BYTES),
        ),
    )


async def test_ingest_new_recording_starts_at_version_one(session: AsyncSession) -> None:
    recording, findings = await catalogue.ingest_recording(
        session,
        recording_id=None,
        metadata_object_key=METADATA_KEY,
        data_object_key=DATA_KEY,
        provenance="lab-a",
        access_classification=AccessClassification.RESTRICTED,
        allowed_use_constraints=[],
        allowed_frequency_min_hz=None,
        allowed_frequency_max_hz=None,
    )

    assert recording.version == 1
    assert findings == []

    fetched = await catalogue.get_recording(session, recording.id)
    assert fetched is not None
    assert fetched.id == recording.id
    assert fetched.sample_count == 100


async def test_ingest_next_version_of_existing_recording(session: AsyncSession) -> None:
    first, _ = await catalogue.ingest_recording(
        session,
        recording_id=None,
        metadata_object_key=METADATA_KEY,
        data_object_key=DATA_KEY,
        provenance="lab-a",
        access_classification=AccessClassification.RESTRICTED,
        allowed_use_constraints=[],
        allowed_frequency_min_hz=None,
        allowed_frequency_max_hz=None,
    )

    second, _ = await catalogue.ingest_recording(
        session,
        recording_id=first.id,
        metadata_object_key=METADATA_KEY,
        data_object_key=DATA_KEY,
        provenance="lab-a-reprocessed",
        access_classification=AccessClassification.RESTRICTED,
        allowed_use_constraints=[],
        allowed_frequency_min_hz=None,
        allowed_frequency_max_hz=None,
    )

    assert second.id == first.id
    assert second.version == 2

    versions = await catalogue.list_recording_versions(session, first.id)
    assert [v.version for v in versions] == [1, 2]

    latest = await catalogue.get_recording(session, first.id)
    assert latest is not None
    assert latest.version == 2


async def test_ingest_new_version_of_unknown_recording_raises_not_found(
    session: AsyncSession,
) -> None:
    with pytest.raises(repository.NotFoundError):
        await catalogue.ingest_recording(
            session,
            recording_id=uuid4(),
            metadata_object_key=METADATA_KEY,
            data_object_key=DATA_KEY,
            provenance=None,
            access_classification=AccessClassification.RESTRICTED,
            allowed_use_constraints=[],
            allowed_frequency_min_hz=None,
            allowed_frequency_max_hz=None,
        )


async def test_ingest_rejects_blocking_findings_without_persisting(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(object_store, "get_object_bytes", lambda key: b"not json")

    with pytest.raises(repository.ValidationRejectedError) as exc_info:
        await catalogue.ingest_recording(
            session,
            recording_id=None,
            metadata_object_key=METADATA_KEY,
            data_object_key=DATA_KEY,
            provenance=None,
            access_classification=AccessClassification.RESTRICTED,
            allowed_use_constraints=[],
            allowed_frequency_min_hz=None,
            allowed_frequency_max_hz=None,
        )
    assert any(f.code == "sigmf_metadata_invalid" for f in exc_info.value.findings)


async def test_get_recording_missing_returns_none(session: AsyncSession) -> None:
    assert await catalogue.get_recording(session, uuid4()) is None


async def test_list_latest_recordings_filters_by_access_classification(
    session: AsyncSession,
) -> None:
    await catalogue.ingest_recording(
        session,
        recording_id=None,
        metadata_object_key=METADATA_KEY,
        data_object_key=DATA_KEY,
        provenance="public-set",
        access_classification=AccessClassification.PUBLIC,
        allowed_use_constraints=[],
        allowed_frequency_min_hz=None,
        allowed_frequency_max_hz=None,
    )
    await catalogue.ingest_recording(
        session,
        recording_id=None,
        metadata_object_key=METADATA_KEY,
        data_object_key=DATA_KEY,
        provenance="controlled-set",
        access_classification=AccessClassification.CONTROLLED,
        allowed_use_constraints=[],
        allowed_frequency_min_hz=None,
        allowed_frequency_max_hz=None,
    )

    public_only = await catalogue.list_latest_recordings(
        session, access_classification=AccessClassification.PUBLIC
    )

    assert {r.provenance for r in public_only} == {"public-set"}


async def test_list_latest_recordings_returns_only_newest_version(session: AsyncSession) -> None:
    first, _ = await catalogue.ingest_recording(
        session,
        recording_id=None,
        metadata_object_key=METADATA_KEY,
        data_object_key=DATA_KEY,
        provenance="lab-a",
        access_classification=AccessClassification.RESTRICTED,
        allowed_use_constraints=[],
        allowed_frequency_min_hz=None,
        allowed_frequency_max_hz=None,
    )
    await catalogue.ingest_recording(
        session,
        recording_id=first.id,
        metadata_object_key=METADATA_KEY,
        data_object_key=DATA_KEY,
        provenance="lab-a-v2",
        access_classification=AccessClassification.RESTRICTED,
        allowed_use_constraints=[],
        allowed_frequency_min_hz=None,
        allowed_frequency_max_hz=None,
    )

    listed = await catalogue.list_latest_recordings(session)

    matching = [r for r in listed if r.id == first.id]
    assert len(matching) == 1
    assert matching[0].version == 2
