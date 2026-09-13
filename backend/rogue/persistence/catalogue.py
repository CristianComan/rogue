"""IQRecording catalogue persistence (M4).

Mirrors ``rogue.persistence.repository``'s Scenario/ScenarioVersion pattern:
each row stores the entire domain object as a JSONB ``document``
(``model_dump(mode="json")``); relational columns duplicate a subset purely
for indexing/filtering. On read the domain object is always reconstructed
from ``document`` alone.

``iq_recordings`` rows are immutable: this module never issues an UPDATE or
DELETE against that table, per docs/architecture/domain-model.md section 5
("Referenced records are deprecated rather than destructively deleted").
Deprecation/retirement of a catalogue entry is not implemented in this
feature — see the M4 completion notes.

Reuses ``rogue.persistence.repository``'s ``NotFoundError`` and
``ValidationRejectedError`` (rather than defining parallel exception types)
so ``rogue.api.errors``'s existing handlers apply to the recordings API
without change.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from rogue.catalogue.ingest import build_ingest_candidate
from rogue.db.models import IQRecordingORM
from rogue.domain.recording import AccessClassification, IQRecording, RecordingKind
from rogue.domain.validation import ValidationFinding, ValidationSeverity
from rogue.persistence.repository import NotFoundError, ValidationRejectedError


def _orm_to_recording(row: IQRecordingORM) -> IQRecording:
    return IQRecording.model_validate(row.document)


async def ingest_recording(
    session: AsyncSession,
    *,
    recording_id: UUID | None,
    metadata_object_key: str,
    data_object_key: str,
    provenance: str | None,
    kind: RecordingKind = RecordingKind.SIGNAL,
    access_classification: AccessClassification,
    allowed_use_constraints: list[str],
    allowed_frequency_min_hz: float | None,
    allowed_frequency_max_hz: float | None,
) -> tuple[IQRecording, list[ValidationFinding]]:
    """Validate and, if it has no BLOCKING findings, persist a new IQRecording version.

    ``recording_id`` omitted registers a brand-new catalogue entry at
    version 1; given, it must reference an existing entry and this becomes
    its next version. Raises ``NotFoundError`` if ``recording_id`` is given
    but no prior version of it exists, ``ValidationRejectedError`` (carrying
    the findings) if the ingest is rejected — mirrors
    ``repository.publish_draft``'s shape.
    """
    if recording_id is not None:
        next_version = await session.scalar(
            select(func.coalesce(func.max(IQRecordingORM.version), 0) + 1).where(
                IQRecordingORM.id == recording_id
            )
        )
        if next_version == 1:
            raise NotFoundError(f"recording {recording_id} does not exist")
    else:
        next_version = 1
    assert next_version is not None

    candidate, findings = await asyncio.to_thread(
        build_ingest_candidate,
        recording_id=recording_id,
        version=next_version,
        metadata_object_key=metadata_object_key,
        data_object_key=data_object_key,
        provenance=provenance,
        kind=kind,
        access_classification=access_classification,
        allowed_use_constraints=allowed_use_constraints,
        allowed_frequency_min_hz=allowed_frequency_min_hz,
        allowed_frequency_max_hz=allowed_frequency_max_hz,
    )
    if candidate is None or any(f.severity == ValidationSeverity.BLOCKING for f in findings):
        raise ValidationRejectedError(findings)

    session.add(
        IQRecordingORM(
            id=candidate.id,
            version=candidate.version,
            document=candidate.model_dump(mode="json"),
            access_classification=candidate.access_classification.value,
            provenance=candidate.provenance,
            created_at=datetime.now(UTC),
        )
    )
    await session.flush()
    return candidate, findings


async def get_recording(
    session: AsyncSession, recording_id: UUID, version: int | None = None
) -> IQRecording | None:
    """Fetch a specific version, or the latest version when ``version`` is omitted."""
    if version is not None:
        row = await session.get(IQRecordingORM, (recording_id, version))
        return None if row is None else _orm_to_recording(row)

    stmt = (
        select(IQRecordingORM)
        .where(IQRecordingORM.id == recording_id)
        .order_by(IQRecordingORM.version.desc())
        .limit(1)
    )
    row = (await session.execute(stmt)).scalar_one_or_none()
    return None if row is None else _orm_to_recording(row)


async def list_recording_versions(session: AsyncSession, recording_id: UUID) -> list[IQRecording]:
    stmt = (
        select(IQRecordingORM)
        .where(IQRecordingORM.id == recording_id)
        .order_by(IQRecordingORM.version)
    )
    result = await session.execute(stmt)
    return [_orm_to_recording(row) for row in result.scalars()]


async def list_latest_recordings(
    session: AsyncSession,
    *,
    access_classification: AccessClassification | None = None,
    provenance_contains: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[IQRecording]:
    """List the latest version of each distinct catalogue entry."""
    latest_version = (
        select(IQRecordingORM.id, func.max(IQRecordingORM.version).label("version"))
        .group_by(IQRecordingORM.id)
        .subquery()
    )
    stmt = (
        select(IQRecordingORM)
        .join(
            latest_version,
            (IQRecordingORM.id == latest_version.c.id)
            & (IQRecordingORM.version == latest_version.c.version),
        )
        .order_by(IQRecordingORM.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    if access_classification is not None:
        stmt = stmt.where(IQRecordingORM.access_classification == access_classification.value)
    if provenance_contains is not None:
        stmt = stmt.where(IQRecordingORM.provenance.ilike(f"%{provenance_contains}%"))
    result = await session.execute(stmt)
    return [_orm_to_recording(row) for row in result.scalars()]
