"""Scenario/draft/version persistence — the only place that talks SQL.

``ScenarioDraft``/``ScenarioVersion`` rows store the *entire* domain object
as a JSONB ``document`` (``model_dump(mode="json")``); relational columns
(``scenario_id``, ``version_number``, ``author``, ``created_at``, ...)
duplicate a subset of that document purely so the database can index,
constrain and filter on them. On read, the domain object is always
reconstructed from ``document`` alone (``Model.model_validate(document)``),
never field-by-field from the relational columns, so there is one source
of truth and no risk of the two drifting apart. See the M2 design note in
docs/architecture/implementation-plan.md for why this is JSONB-backed
rather than a fully normalized schema.

``scenario_versions`` rows are immutable: this module never issues an
UPDATE or DELETE against that table.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from geoalchemy2.shape import from_shape, to_shape
from shapely.geometry import Polygon as ShapelyPolygon
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from rogue.compiler.models import CompilerFinding
from rogue.db.models import IdempotencyKeyORM, ScenarioDraftORM, ScenarioORM, ScenarioVersionORM
from rogue.domain.common import GeoPolygon
from rogue.domain.scenario import Scenario, ScenarioDraft, ScenarioVersion
from rogue.domain.validation import ValidationFinding, ValidationSeverity, validate_scenario_version


class NotFoundError(Exception):
    """Raised when a requested scenario/draft/version does not exist."""


class ConflictError(Exception):
    """Raised on optimistic-concurrency mismatch or idempotency-key reuse."""


class ValidationRejectedError(Exception):
    """Raised when publish is attempted on a draft with BLOCKING findings."""

    def __init__(self, findings: list[ValidationFinding]) -> None:
        super().__init__(f"{len(findings)} blocking validation finding(s)")
        self.findings = findings


class CompilationRejectedError(Exception):
    """Raised when compilation (M6) produces BLOCKING findings; nothing is persisted."""

    def __init__(self, findings: list[CompilerFinding]) -> None:
        super().__init__(f"{len(findings)} blocking compiler finding(s)")
        self.findings = findings


# ---------------------------------------------------------------- geometry


def _polygon_to_geometry(polygon: GeoPolygon) -> Any:
    shell = [(lon, lat) for lon, lat, *_ in polygon.coordinates[0]]
    holes = [[(lon, lat) for lon, lat, *_ in ring] for ring in polygon.coordinates[1:]]
    shapely_polygon = ShapelyPolygon(shell, holes or None)
    return from_shape(shapely_polygon, srid=4326)


def _geometry_to_polygon(value: Any) -> GeoPolygon:
    shapely_polygon = to_shape(value)
    assert isinstance(shapely_polygon, ShapelyPolygon)
    exterior = [tuple(coord) for coord in shapely_polygon.exterior.coords]
    interiors = [[tuple(coord) for coord in ring.coords] for ring in shapely_polygon.interiors]
    return GeoPolygon(coordinates=[exterior, *interiors])


# ---------------------------------------------------------------- scenarios


def _scenario_to_orm(scenario: Scenario) -> ScenarioORM:
    return ScenarioORM(
        id=scenario.id,
        name=scenario.name,
        owner=scenario.owner,
        tags=list(scenario.tags),
        coordinate_system=scenario.coordinate_system,
        area_of_operation=_polygon_to_geometry(scenario.area_of_operation),
        variables=dict(scenario.variables),
        current_version_id=scenario.current_version_id,
        created_at=scenario.created_at,
        updated_at=scenario.updated_at,
    )


def _orm_to_scenario(row: ScenarioORM) -> Scenario:
    return Scenario(
        id=row.id,
        name=row.name,
        owner=row.owner,
        tags=list(row.tags),
        coordinate_system=row.coordinate_system,
        area_of_operation=_geometry_to_polygon(row.area_of_operation),
        variables=dict(row.variables),
        current_version_id=row.current_version_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


async def create_scenario(session: AsyncSession, scenario: Scenario) -> Scenario:
    session.add(_scenario_to_orm(scenario))
    await session.flush()
    return scenario


async def get_scenario(session: AsyncSession, scenario_id: UUID) -> Scenario | None:
    row = await session.get(ScenarioORM, scenario_id)
    return None if row is None else _orm_to_scenario(row)


async def list_scenarios(
    session: AsyncSession,
    *,
    owner: str | None = None,
    tag: str | None = None,
    name_contains: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[Scenario]:
    stmt = select(ScenarioORM).order_by(ScenarioORM.created_at.desc()).limit(limit).offset(offset)
    if owner is not None:
        stmt = stmt.where(ScenarioORM.owner == owner)
    if name_contains is not None:
        stmt = stmt.where(ScenarioORM.name.ilike(f"%{name_contains}%"))
    if tag is not None:
        stmt = stmt.where(ScenarioORM.tags.contains([tag]))
    result = await session.execute(stmt)
    return [_orm_to_scenario(row) for row in result.scalars()]


# ------------------------------------------------------------------ drafts


async def create_draft(session: AsyncSession, draft: ScenarioDraft) -> ScenarioDraft:
    if await session.get(ScenarioORM, draft.scenario_id) is None:
        raise NotFoundError(f"scenario {draft.scenario_id} does not exist")
    session.add(
        ScenarioDraftORM(
            id=draft.id,
            scenario_id=draft.scenario_id,
            base_version_id=draft.base_version_id,
            revision=draft.revision,
            author=draft.author,
            document=draft.model_dump(mode="json"),
            created_at=draft.created_at,
            updated_at=draft.updated_at,
        )
    )
    await session.flush()
    return draft


async def get_draft(
    session: AsyncSession, scenario_id: UUID, draft_id: UUID
) -> ScenarioDraft | None:
    row = await session.get(ScenarioDraftORM, draft_id)
    if row is None or row.scenario_id != scenario_id:
        return None
    return ScenarioDraft.model_validate(row.document)


async def update_draft(
    session: AsyncSession,
    scenario_id: UUID,
    draft_id: UUID,
    updated: ScenarioDraft,
    expected_revision: int,
) -> ScenarioDraft:
    row = await session.get(ScenarioDraftORM, draft_id)
    if row is None or row.scenario_id != scenario_id:
        raise NotFoundError(f"draft {draft_id} does not exist on scenario {scenario_id}")
    if row.revision != expected_revision:
        raise ConflictError(
            f"draft {draft_id} is at revision {row.revision}, not {expected_revision}"
        )

    next_revision = row.revision + 1
    now = datetime.now(UTC)
    saved = updated.model_copy(update={"revision": next_revision, "updated_at": now})

    row.revision = next_revision
    row.author = saved.author
    row.document = saved.model_dump(mode="json")
    row.updated_at = now
    await session.flush()
    return saved


# ---------------------------------------------------------------- versions


def _orm_to_version(row: ScenarioVersionORM) -> ScenarioVersion:
    return ScenarioVersion.model_validate(row.document)


async def get_version(
    session: AsyncSession, scenario_id: UUID, version_number: int
) -> ScenarioVersion | None:
    stmt = select(ScenarioVersionORM).where(
        ScenarioVersionORM.scenario_id == scenario_id,
        ScenarioVersionORM.version_number == version_number,
    )
    row = (await session.execute(stmt)).scalar_one_or_none()
    return None if row is None else _orm_to_version(row)


async def list_versions(session: AsyncSession, scenario_id: UUID) -> list[ScenarioVersion]:
    stmt = (
        select(ScenarioVersionORM)
        .where(ScenarioVersionORM.scenario_id == scenario_id)
        .order_by(ScenarioVersionORM.version_number)
    )
    result = await session.execute(stmt)
    return [_orm_to_version(row) for row in result.scalars()]


async def build_candidate_version(
    session: AsyncSession, scenario_id: UUID, draft_id: UUID
) -> tuple[ScenarioVersion, list[ValidationFinding]]:
    """Build the not-yet-persisted ScenarioVersion a draft would publish as.

    Shared by ``validate_draft`` (check only, never persisted),
    ``publish_draft`` (persisted only if there are no BLOCKING findings) and
    ``rogue.persistence.spectrum`` (M5, also read-only).
    """
    if await session.get(ScenarioORM, scenario_id) is None:
        raise NotFoundError(f"scenario {scenario_id} does not exist")
    draft_row = await session.get(ScenarioDraftORM, draft_id)
    if draft_row is None or draft_row.scenario_id != scenario_id:
        raise NotFoundError(f"draft {draft_id} does not exist on scenario {scenario_id}")

    draft = ScenarioDraft.model_validate(draft_row.document)

    next_number = await session.scalar(
        select(func.coalesce(func.max(ScenarioVersionORM.version_number), 0) + 1).where(
            ScenarioVersionORM.scenario_id == scenario_id
        )
    )

    candidate = ScenarioVersion(
        id=uuid4(),
        scenario_id=scenario_id,
        version_number=next_number,
        zones=draft.zones,
        missions=draft.missions,
        receivers=draft.receivers,
        timeline_events=draft.timeline_events,
        recordings=draft.recordings,
        author=draft.author,
        change_note=None,
    )
    return candidate, validate_scenario_version(candidate)


async def validate_draft(
    session: AsyncSession, scenario_id: UUID, draft_id: UUID
) -> list[ValidationFinding]:
    """Run publish-equivalent validation over a draft without persisting anything."""
    _candidate, findings = await build_candidate_version(session, scenario_id, draft_id)
    return findings


async def publish_draft(
    session: AsyncSession, scenario_id: UUID, draft_id: UUID
) -> ScenarioVersion:
    """Validate a draft and, if it has no BLOCKING findings, publish it.

    Raises ``NotFoundError`` if the scenario/draft don't exist,
    ``ValidationRejectedError`` (carrying the findings) if publish is
    rejected. The draft itself is left untouched either way — publishing
    does not delete or lock it.
    """
    candidate, findings = await build_candidate_version(session, scenario_id, draft_id)

    if any(f.severity == ValidationSeverity.BLOCKING for f in findings):
        raise ValidationRejectedError(findings)

    scenario_row = await session.get(ScenarioORM, scenario_id)
    assert scenario_row is not None  # already validated by build_candidate_version

    published = candidate.model_copy(update={"validation_findings": findings})

    session.add(
        ScenarioVersionORM(
            id=published.id,
            scenario_id=scenario_id,
            version_number=published.version_number,
            schema_version=published.schema_version,
            document=published.model_dump(mode="json"),
            author=published.author,
            change_note=published.change_note,
            created_at=datetime.now(UTC),
        )
    )
    # Flushed separately, and before the update below: nothing tells
    # SQLAlchemy's unit-of-work that scenarios.current_version_id depends on
    # this insert (there's no relationship() wired for that FK direction),
    # so without an explicit ordering point it can flush the UPDATE first
    # and violate the FK.
    await session.flush()

    scenario_row.current_version_id = published.id
    scenario_row.updated_at = datetime.now(UTC)
    await session.flush()
    return published


# -------------------------------------------------------------------- clone


async def clone_scenario(
    session: AsyncSession,
    source_scenario_id: UUID,
    *,
    name: str,
    owner: str,
    source_version_number: int | None = None,
) -> tuple[Scenario, ScenarioDraft]:
    """Create a new Scenario + seed Draft from a source scenario's version.

    Defaults to the source's current published version when
    ``source_version_number`` is omitted.
    """
    source_row = await session.get(ScenarioORM, source_scenario_id)
    if source_row is None:
        raise NotFoundError(f"scenario {source_scenario_id} does not exist")

    source_version: ScenarioVersion | None
    if source_version_number is not None:
        source_version = await get_version(session, source_scenario_id, source_version_number)
        if source_version is None:
            raise NotFoundError(
                f"scenario {source_scenario_id} has no version {source_version_number}"
            )
    elif source_row.current_version_id is not None:
        current_version_row = await session.get(ScenarioVersionORM, source_row.current_version_id)
        source_version = _orm_to_version(current_version_row) if current_version_row else None
    else:
        source_version = None

    now = datetime.now(UTC)
    new_scenario = Scenario(
        id=uuid4(),
        name=name,
        owner=owner,
        tags=list(_orm_to_scenario(source_row).tags),
        coordinate_system=source_row.coordinate_system,
        area_of_operation=_geometry_to_polygon(source_row.area_of_operation),
        variables=dict(source_row.variables),
        current_version_id=None,
        created_at=now,
        updated_at=now,
    )
    await create_scenario(session, new_scenario)

    new_draft = ScenarioDraft(
        id=uuid4(),
        scenario_id=new_scenario.id,
        base_version_id=source_version.id if source_version is not None else None,
        revision=0,
        author=owner,
        zones=source_version.zones if source_version is not None else [],
        missions=source_version.missions if source_version is not None else [],
        receivers=source_version.receivers if source_version is not None else [],
        timeline_events=source_version.timeline_events if source_version is not None else [],
        recordings=source_version.recordings if source_version is not None else [],
        created_at=now,
        updated_at=now,
    )
    await create_draft(session, new_draft)

    return new_scenario, new_draft


# ------------------------------------------------------------ idempotency


def hash_request_body(body: bytes) -> str:
    """Stable hash of a raw request body, used to detect idempotency-key reuse."""
    return hashlib.sha256(body).hexdigest()


async def find_idempotent_response(
    session: AsyncSession, key: str, endpoint: str, request_hash: str
) -> tuple[int, dict[str, Any]] | None:
    """Return the cached (status_code, body) for a replayed request.

    Raises ``ConflictError`` if the same key was used on this endpoint with
    a different request body.
    """
    row = await session.get(IdempotencyKeyORM, (key, endpoint))
    if row is None:
        return None
    if row.request_hash != request_hash:
        raise ConflictError(f"idempotency key {key!r} was already used with a different request")
    return row.status_code, row.response_body


async def store_idempotent_response(
    session: AsyncSession,
    key: str,
    endpoint: str,
    request_hash: str,
    status_code: int,
    response_body: dict[str, Any],
) -> None:
    session.add(
        IdempotencyKeyORM(
            key=key,
            endpoint=endpoint,
            request_hash=request_hash,
            status_code=status_code,
            response_body=response_body,
            created_at=datetime.now(UTC),
        )
    )
    await session.flush()
