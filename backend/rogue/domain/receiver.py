"""Receiver geometry entities.

Per docs/architecture/domain-model.md and rf-model.md section 6: receivers
are scenario data with a geodetic position and a type of MONITOR, TDOA or
AOA_DOA. TDOA/AOA_DOA receivers that must stay time/phase-synchronized
share an ``array_group_id``; AOA_DOA elements additionally carry a
local-frame offset from the array reference point.
"""

from __future__ import annotations

from enum import StrEnum
from uuid import UUID

from pydantic import model_validator

from rogue.domain.common import GeoPoint, IdentifiedMixin


class ReceiverType(StrEnum):
    """Supported receiver roles."""

    MONITOR = "monitor"
    TDOA = "tdoa"
    AOA_DOA = "aoa_doa"


class Receiver(IdentifiedMixin):
    """A single receiver site or array element."""

    name: str
    receiver_type: ReceiverType
    position: GeoPoint

    # TDOA / AOA_DOA arrays: receivers sharing an array_group_id must be
    # jointly time/phase-synchronized by the compiler (rf-model.md section 6).
    array_group_id: UUID | None = None
    element_index: int | None = None
    # AOA_DOA only: element position relative to the array reference point,
    # in a local ENU (east, north, up) frame, meters.
    element_local_offset_m: tuple[float, float, float] | None = None

    @model_validator(mode="after")
    def _array_fields_consistent(self) -> Receiver:
        is_array_type = self.receiver_type in (ReceiverType.TDOA, ReceiverType.AOA_DOA)
        has_array_fields = (
            self.array_group_id is not None or self.element_local_offset_m is not None
        )

        if self.receiver_type == ReceiverType.MONITOR and has_array_fields:
            raise ValueError("MONITOR receivers must not carry array/element fields")
        if is_array_type and self.array_group_id is None:
            raise ValueError(f"{self.receiver_type} receivers require array_group_id")
        if self.receiver_type == ReceiverType.AOA_DOA and self.element_local_offset_m is None:
            raise ValueError("AOA_DOA receivers require element_local_offset_m")
        return self
