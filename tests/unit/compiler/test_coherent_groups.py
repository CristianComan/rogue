"""Unit tests for rogue.compiler.coherent_groups — pure functions, no DB."""

from __future__ import annotations

import math
from uuid import UUID, uuid4

import pytest
from compiler_factories import (
    make_link,
    make_mission,
    make_receiver,
    make_recording,
    make_scenario_version,
)

from rogue.compiler.coherent_groups import (
    compute_delay_offset_s,
    compute_phase_offset_rad,
    expand_occupied_bands,
    reference_receiver,
)
from rogue.domain.common import GeoPoint
from rogue.domain.geometry import SPEED_OF_LIGHT_MPS
from rogue.domain.receiver import ReceiverType
from rogue.domain.recording import RecordingReference
from rogue.domain.rf import RfLinkRole
from rogue.spectrum.models import OccupiedBand

TX = GeoPoint(coordinates=(13.4, 52.5))


def _band(link_id: UUID, mission_id: UUID, recording_ref: RecordingReference) -> OccupiedBand:
    return OccupiedBand(
        mission_id=mission_id,
        link_id=link_id,
        role=RfLinkRole.C2,
        emission_id=uuid4(),
        center_frequency_hz=2_400_000_000.0,
        bandwidth_hz=1_000_000.0,
        freq_min_hz=2_399_500_000.0,
        freq_max_hz=2_400_500_000.0,
        headroom_hz=0.0,
        recording=recording_ref,
    )


# --- reference_receiver -----------------------------------------------------


def test_reference_receiver_picks_lowest_element_index() -> None:
    group_id = uuid4()
    r0 = make_receiver(ReceiverType.TDOA, array_group_id=group_id, element_index=2)
    r1 = make_receiver(ReceiverType.TDOA, array_group_id=group_id, element_index=0)
    r2 = make_receiver(ReceiverType.TDOA, array_group_id=group_id, element_index=1)
    assert reference_receiver([r0, r1, r2]).id == r1.id


def test_reference_receiver_sorts_missing_index_last() -> None:
    group_id = uuid4()
    with_index = make_receiver(ReceiverType.TDOA, array_group_id=group_id, element_index=5)
    no_index = make_receiver(ReceiverType.TDOA, array_group_id=group_id, element_index=None)
    assert reference_receiver([no_index, with_index]).id == with_index.id


# --- compute_delay_offset_s --------------------------------------------------


def test_delay_offset_is_zero_for_the_reference_itself() -> None:
    rx = make_receiver(ReceiverType.TDOA, lon=13.41, lat=52.50)
    assert compute_delay_offset_s(rx, rx, TX) == 0.0


def test_delay_offset_is_positive_when_farther_from_transmitter() -> None:
    near = make_receiver(ReceiverType.TDOA, lon=13.401, lat=52.5)  # close to TX
    far = make_receiver(ReceiverType.TDOA, lon=13.6, lat=52.5)  # far from TX
    delay = compute_delay_offset_s(far, near, TX)
    assert delay > 0.0


# --- compute_phase_offset_rad -------------------------------------------------


def test_phase_offset_is_none_for_tdoa_elements() -> None:
    reference = make_receiver(ReceiverType.TDOA)
    element = make_receiver(ReceiverType.TDOA)
    assert compute_phase_offset_rad(element, reference, TX, 2.4e9) is None


def test_phase_offset_is_zero_for_the_reference_itself() -> None:
    rx = make_receiver(ReceiverType.AOA_DOA, element_local_offset_m=(1.0, 2.0, 0.0))
    assert compute_phase_offset_rad(rx, rx, TX, 2.4e9) == 0.0


def test_phase_offset_matches_projection_along_line_of_sight() -> None:
    # Reference due south of the transmitter (LOS bearing = due north, unit
    # vector (east=0, north=1)); element offset 10m north of reference in
    # the local ENU frame projects fully onto that LOS.
    reference = make_receiver(
        ReceiverType.AOA_DOA, lon=0.0, lat=0.0, element_local_offset_m=(0.0, 0.0, 0.0)
    )
    element = make_receiver(
        ReceiverType.AOA_DOA, lon=0.0, lat=0.0, element_local_offset_m=(0.0, 10.0, 0.0)
    )
    tx = GeoPoint(coordinates=(0.0, 1.0))  # due north of the reference
    carrier_hz = 2.4e9

    phase = compute_phase_offset_rad(element, reference, tx, carrier_hz)

    wavelength_m = SPEED_OF_LIGHT_MPS / carrier_hz
    expected = 2 * math.pi / wavelength_m * 10.0
    assert phase is not None
    assert phase == pytest.approx(expected)


def test_phase_offset_is_near_zero_when_offset_is_perpendicular_to_los() -> None:
    reference = make_receiver(
        ReceiverType.AOA_DOA, lon=0.0, lat=0.0, element_local_offset_m=(0.0, 0.0, 0.0)
    )
    element = make_receiver(
        ReceiverType.AOA_DOA, lon=0.0, lat=0.0, element_local_offset_m=(10.0, 0.0, 0.0)
    )
    tx = GeoPoint(
        coordinates=(0.0, 1.0)
    )  # due north -> LOS unit vector is (0, 1); east offset projects to 0

    phase = compute_phase_offset_rad(element, reference, tx, 2.4e9)

    assert phase is not None
    assert phase == pytest.approx(0.0, abs=1e-6)


# --- expand_occupied_bands ----------------------------------------------------


def test_non_coherent_band_passes_through_unchanged() -> None:
    recording = make_recording()
    link = make_link(recording.reference())
    mission = make_mission([link])
    version = make_scenario_version([mission], [recording.reference()])
    band = _band(link.id, mission.id, recording.reference())

    expanded, findings = expand_occupied_bands([band], version, at_seconds=0.0)

    assert findings == []
    assert expanded == [band]


def test_coherent_band_with_unresolvable_group_passes_through_unchanged() -> None:
    recording = make_recording()
    link = make_link(recording.reference(), array_group_id=uuid4())
    mission = make_mission([link])
    version = make_scenario_version([mission], [recording.reference()])  # no receivers at all
    band = _band(link.id, mission.id, recording.reference())

    expanded, findings = expand_occupied_bands([band], version, at_seconds=0.0)

    assert expanded == [band]


def test_coherent_band_expands_to_one_per_tdoa_element() -> None:
    recording = make_recording()
    group_id = uuid4()
    link = make_link(recording.reference(), array_group_id=group_id)
    mission = make_mission([link])
    rx_a = make_receiver(
        ReceiverType.TDOA, array_group_id=group_id, element_index=0, lon=13.40, lat=52.50
    )
    rx_b = make_receiver(
        ReceiverType.TDOA, array_group_id=group_id, element_index=1, lon=13.60, lat=52.50
    )
    version = make_scenario_version([mission], [recording.reference()], receivers=[rx_a, rx_b])
    band = _band(link.id, mission.id, recording.reference())

    expanded, findings = expand_occupied_bands([band], version, at_seconds=0.0)

    assert findings == []
    assert len(expanded) == 2
    assert {b.array_element_receiver_id for b in expanded} == {rx_a.id, rx_b.id}
    assert all(b.coherent_group_id == group_id for b in expanded)
    assert all(b.phase_offset_rad is None for b in expanded)  # TDOA, not AOA_DOA
    reference_band = next(b for b in expanded if b.array_element_receiver_id == rx_a.id)
    assert reference_band.delay_offset_s == 0.0  # element_index 0 is the reference
    other_band = next(b for b in expanded if b.array_element_receiver_id == rx_b.id)
    assert other_band.delay_offset_s != 0.0


def test_coherent_band_computes_phase_for_aoa_doa_elements() -> None:
    recording = make_recording()
    group_id = uuid4()
    link = make_link(recording.reference(), array_group_id=group_id)
    mission = make_mission([link])
    rx_a = make_receiver(
        ReceiverType.AOA_DOA,
        array_group_id=group_id,
        element_index=0,
        element_local_offset_m=(0.0, 0.0, 0.0),
    )
    rx_b = make_receiver(
        ReceiverType.AOA_DOA,
        array_group_id=group_id,
        element_index=1,
        element_local_offset_m=(0.0, 5.0, 0.0),
    )
    version = make_scenario_version([mission], [recording.reference()], receivers=[rx_a, rx_b])
    band = _band(link.id, mission.id, recording.reference())

    expanded, findings = expand_occupied_bands([band], version, at_seconds=0.0)

    assert findings == []
    reference_band = next(b for b in expanded if b.array_element_receiver_id == rx_a.id)
    other_band = next(b for b in expanded if b.array_element_receiver_id == rx_b.id)
    assert reference_band.phase_offset_rad == 0.0
    assert other_band.phase_offset_rad is not None
