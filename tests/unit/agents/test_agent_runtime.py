"""Tests for AgentRuntime (M8, ADR-008): command dispatch -> adapter call ->
ACK shape, the local watchdog, and cache invocation during PREFLIGHT. No
real NATS broker — commands are fed directly into ``_dispatch``/``_handle``.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from agents.common import cache
from agents.common.agent import AgentRuntime, UnknownAgentModeError, _ChannelContact
from agents.common.air7311_adapter import DeepwaveAIR7311Adapter
from agents.common.x440_adapter import ChannelCapabilityReadback, ChannelConfig, EttusX440Adapter

from rogue.compiler.models import RfWindow
from rogue.execution.adapter import MockSDRAdapter
from rogue.protocol.messages import AgentAck, AgentCommand, AgentCommandKind, RecordingCacheEntry

DEVICE = "sim-1"
CHANNEL = 0


@dataclass
class _FakeMsg:
    data: bytes
    reply: str = "reply-subject"
    responded: bytes | None = None

    async def respond(self, payload: bytes) -> None:
        self.responded = payload


def _command(kind: AgentCommandKind, **overrides: object) -> AgentCommand:
    fields: dict[str, object] = {
        "correlation_id": uuid4(),
        "sequence": 1,
        "kind": kind,
        "device_id": DEVICE,
        "channel_index": CHANNEL,
    }
    fields.update(overrides)
    return AgentCommand(**fields)


def _window() -> RfWindow:
    return RfWindow(
        id=uuid4(),
        window_key="w1",
        start_seconds=0.0,
        end_seconds=10.0,
        center_frequency_hz=2_450_000_000.0,
        bandwidth_hz=20_000_000.0,
        channels=[],
    )


def _runtime(tmp_path: Path) -> AgentRuntime:
    return AgentRuntime(agent_id="sim-agent-test", capabilities=[], cache_dir=tmp_path)


async def test_reserve_dispatch_returns_a_lease_and_records_contact(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    command = _command(AgentCommandKind.RESERVE, run_id=uuid4(), lease_ttl_seconds=30.0)

    result = await runtime._dispatch(command)

    assert result["lease"].device_id == DEVICE
    assert (DEVICE, CHANNEL) in runtime._contacts


async def test_handle_replies_with_an_accepted_ack(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    command = _command(AgentCommandKind.RESERVE, run_id=uuid4(), lease_ttl_seconds=30.0)
    msg = _FakeMsg(data=command.model_dump_json().encode())

    await runtime._handle(msg)

    assert msg.responded is not None
    ack = AgentAck.model_validate_json(msg.responded)
    assert ack.accepted is True
    assert ack.correlation_id == command.correlation_id
    assert ack.lease is not None


async def test_handle_replies_with_a_rejected_ack_on_adapter_failure(tmp_path: Path) -> None:
    from rogue.execution.adapter import MockSDRAdapter

    runtime = _runtime(tmp_path)
    runtime.adapter = MockSDRAdapter(capabilities=[], fail_on={(DEVICE, CHANNEL, "start")})
    command = _command(AgentCommandKind.START)
    msg = _FakeMsg(data=command.model_dump_json().encode())

    await runtime._handle(msg)

    ack = AgentAck.model_validate_json(msg.responded)
    assert ack.accepted is False
    assert ack.error is not None


async def test_preflight_downloads_every_referenced_recording(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime = _runtime(tmp_path)
    seen: list[RecordingCacheEntry] = []
    sample_bytes = b"\x00" * 8 * 100  # 100 cf32_le samples (2 x 4-byte components each)

    async def fake_ensure_cached(cache_dir: Path, entry: RecordingCacheEntry) -> None:
        seen.append(entry)
        cache.meta_path_for(cache_dir, entry.recording_id, entry.version).write_text(
            '{"global": {"core:datatype": "cf32_le", "core:sample_rate": 1000000}}'
        )
        cache.data_path_for(cache_dir, entry.recording_id, entry.version).write_bytes(sample_bytes)

    monkeypatch.setattr(cache, "ensure_cached", fake_ensure_cached)
    entry = RecordingCacheEntry(
        recording_id=uuid4(),
        version=1,
        metadata_object_key="k.sigmf-meta",
        data_object_key="k.sigmf-data",
        sha256_metadata="a" * 64,
        sha256_data="b" * 64,
    )
    command = _command(AgentCommandKind.PREFLIGHT, window=_window(), recordings=[entry])

    result = await runtime._dispatch(command)

    assert result == {}
    assert seen == [entry]


async def test_preflight_builds_iq_recording_from_cached_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The real bug this guards against: PREFLIGHT used to pass an empty
    recordings list to `adapter.preflight()` regardless of what was actually
    cached, which `MockSDRAdapter` silently tolerates but any real
    `StreamingSDRAdapter` (X440/AIR7311) rejects (`len(recordings) != 1`).
    Only surfaced once M10 ran against real hardware for the first time.
    """
    runtime = _runtime(tmp_path)
    received: list[object] = []

    async def fake_preflight(device_id, channel_index, window, recordings) -> None:  # type: ignore[no-untyped-def]
        received.extend(recordings)

    monkeypatch.setattr(runtime.adapter, "preflight", fake_preflight)

    async def fake_ensure_cached(cache_dir: Path, entry: RecordingCacheEntry) -> None:
        cache.meta_path_for(cache_dir, entry.recording_id, entry.version).write_text(
            '{"global": {"core:datatype": "cf32_le", "core:sample_rate": 2000000}}'
        )
        cache.data_path_for(cache_dir, entry.recording_id, entry.version).write_bytes(
            b"\x00" * 8 * 50  # cf32_le = 2 x 4-byte components per sample
        )

    monkeypatch.setattr(cache, "ensure_cached", fake_ensure_cached)
    entry = RecordingCacheEntry(
        recording_id=uuid4(),
        version=1,
        metadata_object_key="k.sigmf-meta",
        data_object_key="k.sigmf-data",
        sha256_metadata="a" * 64,
        sha256_data="b" * 64,
    )
    command = _command(AgentCommandKind.PREFLIGHT, window=_window(), recordings=[entry])

    await runtime._dispatch(command)

    assert len(received) == 1
    recording = received[0]
    assert recording.id == entry.recording_id
    assert recording.sample_format == "cf32_le"
    assert recording.sample_rate_hz == 2_000_000.0
    assert recording.sample_count == 50


async def test_watchdog_emergency_stops_an_armed_channel_past_timeout(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    await runtime.adapter.arm(DEVICE, CHANNEL, start_at_seconds=0.0)
    runtime._contacts[(DEVICE, CHANNEL)] = _ChannelContact(
        last_contact=datetime.now(UTC) - timedelta(seconds=100), timeout_seconds=1.0
    )

    await runtime._check_watchdog()

    status = await runtime.adapter.status(DEVICE, CHANNEL)
    assert status.armed is False
    assert (DEVICE, CHANNEL) not in runtime._contacts


async def test_watchdog_does_not_stop_a_channel_within_timeout(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    await runtime.adapter.arm(DEVICE, CHANNEL, start_at_seconds=0.0)
    runtime._contacts[(DEVICE, CHANNEL)] = _ChannelContact(
        last_contact=datetime.now(UTC), timeout_seconds=100.0
    )

    await runtime._check_watchdog()

    status = await runtime.adapter.status(DEVICE, CHANNEL)
    assert status.armed is True
    assert (DEVICE, CHANNEL) in runtime._contacts


# --- adapter mode selection (M9, ADR-009) ---


class _FakeUHDDevice:
    def num_tx_channels(self) -> int:
        return 1

    def discover_channel(self, channel: int) -> ChannelCapabilityReadback:
        return ChannelCapabilityReadback(
            tunable_ranges_hz=[(1e6, 6e9)], max_usable_bandwidth_hz=400e6, max_sample_rate_hz=500e6
        )

    def configure_channel(self, channel: int, **kwargs: float) -> None:
        pass

    def read_channel_config(self, channel: int) -> ChannelConfig:
        return ChannelConfig(freq_hz=0.0, rate_hz=0.0, bandwidth_hz=0.0, gain_db=0.0)

    def send_chunk(self, channel: int, samples: object) -> None:
        pass

    def end_burst(self, channel: int) -> None:
        pass


def test_simulated_mode_builds_a_mock_adapter(tmp_path: Path) -> None:
    runtime = AgentRuntime(agent_id="a", capabilities=[], cache_dir=tmp_path, mode="simulated")

    assert isinstance(runtime.adapter, MockSDRAdapter)


def test_x440_mode_builds_ettus_adapter_with_the_injected_device(tmp_path: Path) -> None:
    device = _FakeUHDDevice()

    runtime = AgentRuntime(
        agent_id="a", capabilities=[], cache_dir=tmp_path, mode="x440", x440_device=device
    )

    assert isinstance(runtime.adapter, EttusX440Adapter)


def test_air7311_mode_builds_deepwave_adapter_with_the_injected_device(tmp_path: Path) -> None:
    device = _FakeUHDDevice()  # same shape as SoapyDevice — RealDeviceSeam is identical

    runtime = AgentRuntime(
        agent_id="a", capabilities=[], cache_dir=tmp_path, mode="air7311", air7311_device=device
    )

    assert isinstance(runtime.adapter, DeepwaveAIR7311Adapter)


def test_unknown_mode_raises(tmp_path: Path) -> None:
    with pytest.raises(UnknownAgentModeError):
        AgentRuntime(agent_id="a", capabilities=[], cache_dir=tmp_path, mode="not-a-real-mode")


# --- discover()-at-startup (found while planning a real AIR7311 connection) ---


class _NoMessages:
    def __aiter__(self) -> _NoMessages:
        return self

    async def __anext__(self) -> None:
        raise StopAsyncIteration


class _FakeSubscription:
    messages = _NoMessages()

    async def unsubscribe(self) -> None:
        pass


class _FakeNATSForRun:
    async def subscribe(self, subject: str) -> _FakeSubscription:
        return _FakeSubscription()

    async def publish(self, subject: str, payload: bytes) -> None:
        pass


async def test_run_refreshes_capabilities_from_discover_before_first_presence(
    tmp_path: Path,
) -> None:
    device = _FakeUHDDevice()  # reports 1 channel, unlike the constructor's empty list
    runtime = AgentRuntime(
        agent_id="a", capabilities=[], cache_dir=tmp_path, mode="x440", x440_device=device
    )
    stop = asyncio.Event()
    stop.set()  # run() should refresh capabilities, then return immediately

    await runtime.run(_FakeNATSForRun(), stop)  # type: ignore[arg-type]

    assert len(runtime.capabilities) == 1
    assert runtime.capabilities[0].max_usable_bandwidth_hz == 400e6
