"""Tests for receiver geometry entities and MONITOR/TDOA/AOA_DOA invariants."""

from __future__ import annotations

from uuid import uuid4

import pytest
from factories import make_receiver
from pydantic import ValidationError

from rogue.domain.receiver import ReceiverType


def test_monitor_receiver_rejects_array_fields() -> None:
    with pytest.raises(ValidationError):
        make_receiver(ReceiverType.MONITOR, array_group_id=uuid4())


def test_tdoa_receiver_requires_array_group_id() -> None:
    with pytest.raises(ValidationError):
        make_receiver(ReceiverType.TDOA, array_group_id=None)


def test_aoa_doa_receiver_requires_element_offset() -> None:
    with pytest.raises(ValidationError):
        make_receiver(ReceiverType.AOA_DOA, element_local_offset_m=None)


@pytest.mark.parametrize(
    "receiver_type", [ReceiverType.MONITOR, ReceiverType.TDOA, ReceiverType.AOA_DOA]
)
def test_valid_receiver_construction(receiver_type: ReceiverType) -> None:
    receiver = make_receiver(receiver_type)
    assert receiver.receiver_type == receiver_type
