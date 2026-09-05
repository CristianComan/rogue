"""Tests for AgentRuntime (M8, ADR-008): command dispatch -> adapter call ->
ACK shape, the local watchdog, and cache invocation during PREFLIGHT. No
real NATS broker — commands are fed directly into ``_dispatch``/``_handle``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from agents.common import cache
from agents.common.agent import AgentRuntime, _ChannelContact

from rogue.compiler.models import RfWindow
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

    async def fake_ensure_cached(cache_dir: Path, entry: RecordingCacheEntry) -> None:
        seen.append(entry)

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
