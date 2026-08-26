"""Repository tests against a real Postgres/PostGIS (see conftest.py)."""

from __future__ import annotations

import pytest
from persistence_factories import (
    area_polygon,
    make_draft,
    make_mission,
    make_scenario,
    recording_reference,
)
from sqlalchemy.ext.asyncio import AsyncSession

from rogue.domain.validation import ValidationSeverity
from rogue.persistence import repository


async def test_create_and_get_scenario_round_trips_geometry(session: AsyncSession) -> None:
    scenario = make_scenario()

    await repository.create_scenario(session, scenario)
    fetched = await repository.get_scenario(session, scenario.id)

    assert fetched is not None
    assert fetched.id == scenario.id
    assert fetched.name == scenario.name
    assert fetched.tags == scenario.tags
    original_ring = area_polygon().coordinates[0]
    fetched_ring = fetched.area_of_operation.coordinates[0]
    assert [(round(lon, 6), round(lat, 6)) for lon, lat in original_ring] == [
        (round(lon, 6), round(lat, 6)) for lon, lat in fetched_ring
    ]


async def test_get_scenario_missing_returns_none(session: AsyncSession) -> None:
    from uuid import uuid4

    assert await repository.get_scenario(session, uuid4()) is None


async def test_list_scenarios_filters_by_owner_and_tag(session: AsyncSession) -> None:
    await repository.create_scenario(session, make_scenario(owner="alice", tags=["lab-a"]))
    await repository.create_scenario(session, make_scenario(owner="bob", tags=["lab-b"]))

    alice_scenarios = await repository.list_scenarios(session, owner="alice")
    assert {s.owner for s in alice_scenarios} == {"alice"}

    lab_b_scenarios = await repository.list_scenarios(session, tag="lab-b")
    assert {s.owner for s in lab_b_scenarios} == {"bob"}


async def test_create_draft_on_missing_scenario_raises_not_found(session: AsyncSession) -> None:
    from uuid import uuid4

    with pytest.raises(repository.NotFoundError):
        await repository.create_draft(session, make_draft(scenario_id=uuid4()))


async def test_create_and_get_draft_round_trip(session: AsyncSession) -> None:
    scenario = make_scenario()
    await repository.create_scenario(session, scenario)
    draft = make_draft(scenario_id=scenario.id)

    await repository.create_draft(session, draft)
    fetched = await repository.get_draft(session, scenario.id, draft.id)

    assert fetched is not None
    assert fetched.author == draft.author
    assert fetched.revision == 0


async def test_update_draft_rejects_stale_revision(session: AsyncSession) -> None:
    scenario = make_scenario()
    await repository.create_scenario(session, scenario)
    draft = make_draft(scenario_id=scenario.id)
    await repository.create_draft(session, draft)

    with pytest.raises(repository.ConflictError):
        await repository.update_draft(
            session, scenario.id, draft.id, draft.model_copy(update={"author": "eve"}), 5
        )


async def test_update_draft_bumps_revision_on_match(session: AsyncSession) -> None:
    scenario = make_scenario()
    await repository.create_scenario(session, scenario)
    draft = make_draft(scenario_id=scenario.id)
    await repository.create_draft(session, draft)

    updated = await repository.update_draft(
        session, scenario.id, draft.id, draft.model_copy(update={"author": "eve"}), 0
    )

    assert updated.revision == 1
    assert updated.author == "eve"


async def test_publish_valid_draft_creates_version_and_updates_scenario(
    session: AsyncSession,
) -> None:
    scenario = make_scenario()
    await repository.create_scenario(session, scenario)

    ref = recording_reference()
    draft = make_draft(scenario_id=scenario.id, missions=[make_mission(ref)], recordings=[ref])
    await repository.create_draft(session, draft)

    published = await repository.publish_draft(session, scenario.id, draft.id)

    assert published.version_number == 1
    assert all(f.severity != ValidationSeverity.BLOCKING for f in published.validation_findings)

    scenario_after = await repository.get_scenario(session, scenario.id)
    assert scenario_after is not None
    assert scenario_after.current_version_id == published.id


async def test_validate_draft_does_not_persist_anything(session: AsyncSession) -> None:
    scenario = make_scenario()
    await repository.create_scenario(session, scenario)

    ref = recording_reference()
    draft = make_draft(scenario_id=scenario.id, missions=[make_mission(ref)], recordings=[])
    await repository.create_draft(session, draft)

    findings = await repository.validate_draft(session, scenario.id, draft.id)

    assert any(f.code == "dangling_recording_reference" for f in findings)
    assert await repository.list_versions(session, scenario.id) == []


async def test_publish_rejects_dangling_recording_reference(session: AsyncSession) -> None:
    scenario = make_scenario()
    await repository.create_scenario(session, scenario)

    ref = recording_reference()
    draft = make_draft(scenario_id=scenario.id, missions=[make_mission(ref)], recordings=[])
    await repository.create_draft(session, draft)

    with pytest.raises(repository.ValidationRejectedError) as exc_info:
        await repository.publish_draft(session, scenario.id, draft.id)

    assert any(f.code == "dangling_recording_reference" for f in exc_info.value.findings)
    assert await repository.list_versions(session, scenario.id) == []


async def test_get_and_list_versions(session: AsyncSession) -> None:
    scenario = make_scenario()
    await repository.create_scenario(session, scenario)
    draft = make_draft(scenario_id=scenario.id)
    await repository.create_draft(session, draft)
    published = await repository.publish_draft(session, scenario.id, draft.id)

    fetched = await repository.get_version(session, scenario.id, published.version_number)
    assert fetched == published

    all_versions = await repository.list_versions(session, scenario.id)
    assert [v.version_number for v in all_versions] == [1]


async def test_clone_scenario_from_current_version(session: AsyncSession) -> None:
    scenario = make_scenario()
    await repository.create_scenario(session, scenario)
    draft = make_draft(scenario_id=scenario.id)
    await repository.create_draft(session, draft)
    await repository.publish_draft(session, scenario.id, draft.id)

    new_scenario, new_draft = await repository.clone_scenario(
        session, scenario.id, name="cloned", owner="clone-owner"
    )

    assert new_scenario.id != scenario.id
    assert new_scenario.name == "cloned"
    assert new_draft.scenario_id == new_scenario.id
    assert new_draft.base_version_id is not None


async def test_idempotency_replay_and_conflict(session: AsyncSession) -> None:
    body_hash = repository.hash_request_body(b'{"a": 1}')
    await repository.store_idempotent_response(
        session, "key-1", "POST /scenarios", body_hash, 201, {"id": "abc"}
    )

    replayed = await repository.find_idempotent_response(
        session, "key-1", "POST /scenarios", body_hash
    )
    assert replayed == (201, {"id": "abc"})

    with pytest.raises(repository.ConflictError):
        await repository.find_idempotent_response(
            session, "key-1", "POST /scenarios", repository.hash_request_body(b'{"a": 2}')
        )
