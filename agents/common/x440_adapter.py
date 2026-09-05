"""EttusX440Adapter: the first real `SDRAdapter` implementation (M9, ADR-009),
against UHD's native Python bindings per ADR-005 (not `SoapyUHD`). Vendor-
agnostic behaviour (lease bookkeeping, the real-TX safety gate, bounded-
chunk cache-file streaming) lives in `agents.common.sdr_adapter_base.
StreamingSDRAdapter` — this module only supplies the UHD-specific device
seam. See that module's docstring for this pass's explicit scope limits
(single device, one recording per channel, `cf32_le` only, no looping).

**Not verified against real UHD or physical X440 hardware in this change.**
This development environment has neither the `uhd` Python package nor a
physical device attached — see ADR-009 for the explicit scope record.
`_open_real_uhd_device` is the one function a real lab run needs to confirm
against the installed `uhd` package's actual API (its exact call shapes
have had some churn across UHD releases); everything else is unit-tested
against a fake `UHDDevice` in `tests/unit/agents/test_x440_adapter.py`.
"""

from __future__ import annotations

from pathlib import Path

from agents.common.sdr_adapter_base import (
    ChannelCapabilityReadback,
    ChannelConfig,
    RealDeviceSeam,
    RealTxNotAuthorizedError,
    StreamingSDRAdapter,
)
from rogue.compiler.models import PhysicalTxChannelCapability

__all__ = [
    "ChannelCapabilityReadback",
    "ChannelConfig",
    "EttusX440Adapter",
    "RealTxNotAuthorizedError",
    "UHDDevice",
]

# Same shape as RealDeviceSeam; aliased for readability at this module's
# call sites and for agents/common/agent.py's constructor parameter name.
UHDDevice = RealDeviceSeam


def _open_real_uhd_device(device_args: str) -> RealDeviceSeam:
    """The one place that touches the real `uhd` package — imported lazily
    so `EttusX440Adapter` stays testable/importable without it.

    **Unverified**: written against UHD's documented Python API shape, not
    exercised against a real installation or device in this change (ADR-009).
    """
    import uhd  # noqa: PLC0415 - intentionally lazy, see module docstring

    usrp = uhd.usrp.MultiUSRP(device_args)
    streamers: dict[int, object] = {}

    def _streamer(channel: int) -> object:
        if channel not in streamers:
            stream_args = uhd.usrp.StreamArgs("fc32", "sc16")
            stream_args.channels = [channel]
            streamers[channel] = usrp.get_tx_stream(stream_args)
        return streamers[channel]

    class _RealUHDDevice:
        def num_tx_channels(self) -> int:
            return int(usrp.get_tx_num_channels())

        def discover_channel(self, channel: int) -> ChannelCapabilityReadback:
            freq_range = usrp.get_tx_freq_range(channel)
            bw_range = usrp.get_tx_bandwidth_range(channel)
            rate_range = usrp.get_tx_rates(channel)
            return ChannelCapabilityReadback(
                tunable_ranges_hz=[(freq_range.start(), freq_range.stop())],
                max_usable_bandwidth_hz=bw_range.stop(),
                max_sample_rate_hz=rate_range.stop(),
            )

        def configure_channel(
            self,
            channel: int,
            *,
            freq_hz: float,
            rate_hz: float,
            bandwidth_hz: float,
            gain_db: float,
        ) -> None:
            usrp.set_tx_rate(rate_hz, channel)
            usrp.set_tx_freq(uhd.types.TuneRequest(freq_hz), channel)
            usrp.set_tx_bandwidth(bandwidth_hz, channel)
            usrp.set_tx_gain(gain_db, channel)

        def read_channel_config(self, channel: int) -> ChannelConfig:
            return ChannelConfig(
                freq_hz=usrp.get_tx_freq(channel),
                rate_hz=usrp.get_tx_rate(channel),
                bandwidth_hz=usrp.get_tx_bandwidth(channel),
                gain_db=usrp.get_tx_gain(channel),
            )

        def send_chunk(self, channel: int, samples: object) -> None:
            metadata = uhd.types.TXMetadata()
            _streamer(channel).send(samples, metadata)  # type: ignore[attr-defined]

        def end_burst(self, channel: int) -> None:
            import numpy as np

            metadata = uhd.types.TXMetadata()
            metadata.end_of_burst = True
            _streamer(channel).send(np.zeros(0, dtype=np.complex64), metadata)  # type: ignore[attr-defined]

    return _RealUHDDevice()


class EttusX440Adapter(StreamingSDRAdapter):
    """Real `SDRAdapter` implementation for one Ettus X440 unit."""

    def __init__(
        self,
        capabilities: list[PhysicalTxChannelCapability],
        cache_dir: Path,
        device: UHDDevice | None = None,
        device_args: str = "",
        enable_real_tx: bool = False,
    ) -> None:
        super().__init__(
            capabilities=capabilities,
            cache_dir=cache_dir,
            device=device or _open_real_uhd_device(device_args),
            device_family="x440",
            enable_real_tx=enable_real_tx,
        )
