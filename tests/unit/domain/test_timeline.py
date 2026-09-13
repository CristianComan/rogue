"""Tests for the discriminated timeline event union."""

from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

from pydantic import TypeAdapter

from rogue.domain.timeline import (
    AbsoluteTimelineEvent,
    MissionRelativeAnchor,
    MissionRelativeTimelineEvent,
    SafetyEventKind,
    SafetyTimelineEvent,
    TimelineEvent,
)

_adapter: TypeAdapter[TimelineEvent] = TypeAdapter(TimelineEvent)


def test_absolute_event_round_trips_through_discriminated_union() -> None:
    event = AbsoluteTimelineEvent(scenario_time_offset=timedelta(minutes=2))

    dumped = _adapter.dump_python(event, mode="json")
    restored = _adapter.validate_python(dumped)

    assert isinstance(restored, AbsoluteTimelineEvent)
    assert restored.scenario_time_offset == timedelta(minutes=2)


def test_mission_relative_event_round_trips() -> None:
    mission_id = uuid4()
    event = MissionRelativeTimelineEvent(
        mission_id=mission_id,
        anchor=MissionRelativeAnchor.WAYPOINT,
        waypoint_sequence_index=3,
    )

    restored = _adapter.validate_python(_adapter.dump_python(event, mode="json"))

    assert isinstance(restored, MissionRelativeTimelineEvent)
    assert restored.mission_id == mission_id
    assert restored.waypoint_sequence_index == 3


def test_safety_event_discriminates_correctly() -> None:
    event = SafetyTimelineEvent(safety_kind=SafetyEventKind.EMERGENCY_STOP)

    restored = _adapter.validate_python(_adapter.dump_python(event, mode="json"))

    assert isinstance(restored, SafetyTimelineEvent)
    assert restored.safety_kind == SafetyEventKind.EMERGENCY_STOP
