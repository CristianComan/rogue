"""The real Agent runtime (M8, ADR-008) — separate from `main.py`'s process
bootstrap/signal handling. Owns one `SDRAdapter` (`mode` selects
`MockSDRAdapter` for simulated hardware, `EttusX440Adapter` for a real
X440 (M9/ADR-009), or `DeepwaveAIR7311Adapter` for a real AIR7311
(M10/ADR-010)), answers commands on its own NATS command subject,
publishes presence/telemetry, and runs a local watchdog independent of
control-plane reachability (`sdr-architecture.md` §7, CLAUDE.md rule 12).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from nats.aio.client import Client as NATSClient
from nats.aio.msg import Msg

from agents.common import cache
from agents.common.air7311_adapter import DeepwaveAIR7311Adapter, SoapyDevice
from agents.common.x440_adapter import EttusX440Adapter, UHDDevice
from rogue.catalogue.sigmf import bytes_per_sample, parse_metadata
from rogue.compiler.models import PhysicalTxChannelCapability
from rogue.domain.recording import IQRecording
from rogue.execution.adapter import AdapterOperationError, MockSDRAdapter, SDRAdapter
from rogue.protocol.messages import (
    AgentAck,
    AgentCommand,
    AgentCommandKind,
    AgentPresence,
    AgentTelemetry,
    RecordingCacheEntry,
)
from rogue.protocol.subjects import PRESENCE_SUBJECT, agent_command_subject, agent_telemetry_subject
from rogue.settings import settings


def _load_cached_recording(cache_dir: Path, entry: RecordingCacheEntry) -> IQRecording:
    """Rebuild the `IQRecording` a real `SDRAdapter.preflight()` needs from
    what `cache.ensure_cached` already downloaded for this entry.

    `RecordingCacheEntry` (the wire-protocol shape) deliberately omits
    `sample_format`/`sample_rate_hz`/`sample_count`/`duration_s` — the Agent
    has no catalogue-database access (ADR-008), so those come from the
    cached `.sigmf-meta` bytes and the downloaded `.sigmf-data` file size
    instead of a second round trip to the API.
    """
    meta_path = cache.meta_path_for(cache_dir, entry.recording_id, entry.version)
    data_path = cache.data_path_for(cache_dir, entry.recording_id, entry.version)
    parsed = parse_metadata(meta_path.read_bytes())
    if parsed.errors or parsed.sample_rate_hz is None:
        raise AdapterOperationError(
            str(entry.recording_id), -1, f"cached SigMF metadata is invalid: {parsed.errors}"
        )
    sample_size = bytes_per_sample(parsed.sample_format)
    if sample_size is None:
        raise AdapterOperationError(
            str(entry.recording_id),
            -1,
            f"cached SigMF metadata has unsupported core:datatype {parsed.sample_format!r}",
        )
    sample_count = data_path.stat().st_size // sample_size
    return IQRecording(
        id=entry.recording_id,
        version=entry.version,
        metadata_object_key=entry.metadata_object_key,
        data_object_key=entry.data_object_key,
        sha256_metadata=entry.sha256_metadata,
        sha256_data=entry.sha256_data,
        sample_format=parsed.sample_format,
        sample_rate_hz=parsed.sample_rate_hz,
        sample_count=sample_count,
        duration_s=sample_count / parsed.sample_rate_hz,
        center_frequency_hz=parsed.center_frequency_hz,
    )


class UnknownAgentModeError(ValueError):
    """Raised when `ROGUE_AGENT_MODE` doesn't match a known adapter."""


logger = logging.getLogger("rogue.agent.runtime")

PRESENCE_INTERVAL_SECONDS = 5.0
TELEMETRY_INTERVAL_SECONDS = 5.0
# A channel armed/transmitting with no control-plane contact for this many
# multiples of its own lease TTL is stopped locally — independent of
# whether the central lease-sweep (rogue.execution.lease_sweep) is even
# reachable (ADR-008).
WATCHDOG_TIMEOUT_MULTIPLIER = 3.0
WATCHDOG_POLL_INTERVAL_SECONDS = 2.0


@dataclass
class _ChannelContact:
    last_contact: datetime
    timeout_seconds: float


class AgentRuntime:
    def __init__(
        self,
        agent_id: str,
        capabilities: list[PhysicalTxChannelCapability],
        cache_dir: Path,
        mode: str = "simulated",
        x440_device: UHDDevice | None = None,
        air7311_device: SoapyDevice | None = None,
    ) -> None:
        self.agent_id = agent_id
        self.mode = mode
        self.capabilities = capabilities
        self.cache_dir = cache_dir
        self.adapter: SDRAdapter = self._build_adapter(
            mode, capabilities, cache_dir, x440_device, air7311_device
        )
        self._contacts: dict[tuple[str, int], _ChannelContact] = {}

    @staticmethod
    def _build_adapter(
        mode: str,
        capabilities: list[PhysicalTxChannelCapability],
        cache_dir: Path,
        x440_device: UHDDevice | None,
        air7311_device: SoapyDevice | None,
    ) -> SDRAdapter:
        if mode == "simulated":
            return MockSDRAdapter(capabilities=capabilities)
        if mode == "x440":
            # x440_device lets tests inject a fake UHDDevice; left None it
            # opens a real one via settings.x440_device_args (requires the
            # uhd package — see agents/common/x440_adapter.py's docstring).
            return EttusX440Adapter(
                capabilities=capabilities,
                cache_dir=cache_dir,
                device=x440_device,
                device_args=settings.x440_device_args or "",
                enable_real_tx=settings.enable_real_tx,
            )
        if mode == "air7311":
            # air7311_device lets tests inject a fake SoapyDevice; left None
            # it opens a real one via settings.air7311_device_args (requires
            # SoapySDR's Python bindings — see
            # agents/common/air7311_adapter.py's docstring).
            return DeepwaveAIR7311Adapter(
                capabilities=capabilities,
                cache_dir=cache_dir,
                device=air7311_device,
                device_args=settings.air7311_device_args or "",
                enable_real_tx=settings.enable_real_tx,
            )
        raise UnknownAgentModeError(f"unknown ROGUE_AGENT_MODE {mode!r}")

    def _touch(self, key: tuple[str, int], ttl_seconds: float | None = None) -> None:
        now = datetime.now(UTC)
        if ttl_seconds is not None:
            self._contacts[key] = _ChannelContact(
                last_contact=now, timeout_seconds=ttl_seconds * WATCHDOG_TIMEOUT_MULTIPLIER
            )
        elif key in self._contacts:
            self._contacts[key].last_contact = now

    async def _dispatch(self, command: AgentCommand) -> dict[str, object]:
        device_id, channel_index = command.device_id, command.channel_index
        key = (device_id, channel_index)
        adapter = self.adapter
        kind = command.kind

        if kind == AgentCommandKind.RESERVE:
            assert command.run_id is not None
            assert command.lease_ttl_seconds is not None
            lease = await adapter.reserve(
                device_id, channel_index, command.run_id, command.lease_ttl_seconds
            )
            self._touch(key, command.lease_ttl_seconds)
            return {"lease": lease}
        if kind == AgentCommandKind.RENEW_LEASE:
            assert command.lease is not None
            assert command.lease_ttl_seconds is not None
            lease = await adapter.renew(command.lease, command.lease_ttl_seconds)
            self._touch(key, command.lease_ttl_seconds)
            return {"lease": lease}
        if kind == AgentCommandKind.RELEASE:
            assert command.lease is not None
            await adapter.release(command.lease)
            self._contacts.pop(key, None)
            return {}
        if kind == AgentCommandKind.PREFLIGHT:
            assert command.window is not None
            for entry in command.recordings or []:
                await cache.ensure_cached(self.cache_dir, entry)
            recordings = [
                _load_cached_recording(self.cache_dir, entry) for entry in command.recordings or []
            ]
            await adapter.preflight(device_id, channel_index, command.window, recordings)
            return {}
        if kind == AgentCommandKind.CONFIGURE:
            assert command.window is not None
            await adapter.configure(device_id, channel_index, command.window)
            return {}
        if kind == AgentCommandKind.ARM:
            assert command.start_at_seconds is not None
            await adapter.arm(device_id, channel_index, command.start_at_seconds)
            self._touch(key)
            return {}
        if kind == AgentCommandKind.START:
            await adapter.start(device_id, channel_index)
            self._touch(key)
            return {}
        if kind == AgentCommandKind.STOP:
            await adapter.stop(device_id, channel_index)
            self._contacts.pop(key, None)
            return {}
        if kind == AgentCommandKind.EMERGENCY_STOP:
            await adapter.emergency_stop(device_id, channel_index)
            self._contacts.pop(key, None)
            return {}
        if kind == AgentCommandKind.STATUS:
            status = await adapter.status(device_id, channel_index)
            return {"status": status}
        raise ValueError(f"unhandled command kind {kind!r}")

    async def _handle(self, msg: Msg) -> None:
        command = AgentCommand.model_validate_json(msg.data)
        try:
            result = await self._dispatch(command)
            ack = AgentAck(
                correlation_id=command.correlation_id, sequence=command.sequence, **result
            )
        except (AdapterOperationError, cache.CacheVerificationError) as exc:
            ack = AgentAck(
                correlation_id=command.correlation_id,
                sequence=command.sequence,
                accepted=False,
                error=str(exc),
            )
        if msg.reply:
            await msg.respond(ack.model_dump_json().encode())

    async def _command_loop(self, subscription: object) -> None:
        async for msg in subscription.messages:  # type: ignore[attr-defined]
            try:
                await self._handle(msg)
            except Exception:
                logger.exception("failed to handle a command message")

    async def _presence_loop(self, nc: NATSClient, stop: asyncio.Event) -> None:
        while not stop.is_set():
            presence = AgentPresence(
                agent_id=self.agent_id, mode=self.mode, capabilities=self.capabilities
            )
            await nc.publish(PRESENCE_SUBJECT, presence.model_dump_json().encode())
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=PRESENCE_INTERVAL_SECONDS)

    async def _telemetry_loop(self, nc: NATSClient, stop: asyncio.Event) -> None:
        while not stop.is_set():
            for device_id, channel_index in list(self._contacts.keys()):
                status = await self.adapter.status(device_id, channel_index)
                telemetry = AgentTelemetry(
                    agent_id=self.agent_id,
                    device_id=device_id,
                    channel_index=channel_index,
                    status=status,
                )
                await nc.publish(
                    agent_telemetry_subject(self.agent_id), telemetry.model_dump_json().encode()
                )
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=TELEMETRY_INTERVAL_SECONDS)

    async def _check_watchdog(self) -> None:
        now = datetime.now(UTC)
        for (device_id, channel_index), contact in list(self._contacts.items()):
            if (now - contact.last_contact).total_seconds() <= contact.timeout_seconds:
                continue
            status = await self.adapter.status(device_id, channel_index)
            if status.armed or status.transmitting:
                logger.warning(
                    "local watchdog timeout for %s:%s; emergency-stopping without "
                    "control-plane contact",
                    device_id,
                    channel_index,
                )
                await self.adapter.emergency_stop(device_id, channel_index)
            self._contacts.pop((device_id, channel_index), None)

    async def _watchdog_loop(self, stop: asyncio.Event) -> None:
        while not stop.is_set():
            await self._check_watchdog()
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=WATCHDOG_POLL_INTERVAL_SECONDS)

    async def run(self, nc: NATSClient, stop: asyncio.Event) -> None:
        """Runs until `stop` is set."""
        # Refresh from the adapter's own discover() before the first presence
        # publish — CLAUDE.md rule 10: runtime discovery is authoritative, not
        # whatever static slice main.py constructed this runtime with. A no-op
        # for MockSDRAdapter (discover() just echoes back what it was given);
        # for a real adapter this replaces illustrative defaults with the
        # hardware's actual reported ranges. Left as the constructor-supplied
        # value if discover() comes back empty, rather than wiping to nothing.
        self.capabilities = await self.adapter.discover() or self.capabilities
        subscription = await nc.subscribe(agent_command_subject(self.agent_id))
        tasks = [
            asyncio.create_task(self._command_loop(subscription)),
            asyncio.create_task(self._presence_loop(nc, stop)),
            asyncio.create_task(self._telemetry_loop(nc, stop)),
            asyncio.create_task(self._watchdog_loop(stop)),
        ]
        try:
            await stop.wait()
        finally:
            await subscription.unsubscribe()
            for task in tasks:
                task.cancel()
            for task in tasks:
                with contextlib.suppress(asyncio.CancelledError):
                    await task
