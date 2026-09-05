"""DeepwaveAIR7311Adapter: the second real `SDRAdapter` implementation (M10,
ADR-010), against native SoapySDR per ADR-005 (AIR7311 is SoapySDR-native;
this is not the `SoapyUHD`/X440 wrapper path). Vendor-agnostic behaviour
(lease bookkeeping, the real-TX safety gate, bounded-chunk cache-file
streaming) lives in `agents.common.sdr_adapter_base.StreamingSDRAdapter` —
this module only supplies the SoapySDR-specific device seam. See that
module's docstring for this pass's explicit scope limits (single device,
one recording per channel, `cf32_le` only, no looping).

**Not verified against real SoapySDR or physical AIR7311 hardware in this
change.** This development environment has neither SoapySDR's Python
bindings nor a physical device attached — see ADR-010 for the explicit
scope record. Unlike `uhd`, SoapySDR's Python bindings are not a normal
pip-installable package (built against the system SoapySDR C++ library —
see `docs/architecture/deployment.md` §7); a real AIR7311 Agent host
provisions them separately, outside this repository's own packaging.
`_open_real_soapy_device` is the one function a real lab run needs to
confirm against the installed SoapySDR version's actual API; everything
else is unit-tested against a fake `SoapyDevice` in
`tests/unit/agents/test_air7311_adapter.py`.
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
    "DeepwaveAIR7311Adapter",
    "RealTxNotAuthorizedError",
    "SoapyDevice",
]

# Same shape as RealDeviceSeam; aliased for readability at this module's
# call sites and for agents/common/agent.py's constructor parameter name.
SoapyDevice = RealDeviceSeam


def _open_real_soapy_device(device_args: str) -> RealDeviceSeam:
    """The one place that touches the real SoapySDR bindings — imported
    lazily so `DeepwaveAIR7311Adapter` stays testable/importable without
    them.

    **Unverified**: written against SoapySDR's documented Python API shape
    (`SoapySDR.Device`, `setFrequency`/`setSampleRate`/`setBandwidth`/
    `setGain`, `setupStream`/`writeStream`), not exercised against a real
    installation or device in this change (ADR-010).
    """
    import SoapySDR  # noqa: PLC0415 - intentionally lazy, see module docstring
    from SoapySDR import SOAPY_SDR_CF32, SOAPY_SDR_TX

    device = SoapySDR.Device(device_args)
    streams: dict[int, object] = {}

    def _stream(channel: int) -> object:
        if channel not in streams:
            tx_stream = device.setupStream(SOAPY_SDR_TX, SOAPY_SDR_CF32, [channel])
            device.activateStream(tx_stream)
            streams[channel] = tx_stream
        return streams[channel]

    class _RealSoapyDevice:
        def num_tx_channels(self) -> int:
            return int(device.getNumChannels(SOAPY_SDR_TX))

        def discover_channel(self, channel: int) -> ChannelCapabilityReadback:
            freq_range = device.getFrequencyRange(SOAPY_SDR_TX, channel)
            bw_range = device.getBandwidthRange(SOAPY_SDR_TX, channel)
            rates = device.listSampleRates(SOAPY_SDR_TX, channel)
            return ChannelCapabilityReadback(
                tunable_ranges_hz=[(r.minimum(), r.maximum()) for r in freq_range],
                max_usable_bandwidth_hz=max((r.maximum() for r in bw_range), default=0.0),
                max_sample_rate_hz=max(rates, default=0.0),
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
            device.setSampleRate(SOAPY_SDR_TX, channel, rate_hz)
            device.setFrequency(SOAPY_SDR_TX, channel, freq_hz)
            device.setBandwidth(SOAPY_SDR_TX, channel, bandwidth_hz)
            device.setGain(SOAPY_SDR_TX, channel, gain_db)

        def read_channel_config(self, channel: int) -> ChannelConfig:
            return ChannelConfig(
                freq_hz=device.getFrequency(SOAPY_SDR_TX, channel),
                rate_hz=device.getSampleRate(SOAPY_SDR_TX, channel),
                bandwidth_hz=device.getBandwidth(SOAPY_SDR_TX, channel),
                gain_db=device.getGain(SOAPY_SDR_TX, channel),
            )

        def send_chunk(self, channel: int, samples: object) -> None:
            device.writeStream(_stream(channel), [samples], len(samples))  # type: ignore[arg-type]

        def end_burst(self, channel: int) -> None:
            stream = streams.get(channel)
            if stream is not None:
                device.deactivateStream(stream)
                device.closeStream(stream)
                del streams[channel]

    return _RealSoapyDevice()


class DeepwaveAIR7311Adapter(StreamingSDRAdapter):
    """Real `SDRAdapter` implementation for one Deepwave AIR7311 unit."""

    def __init__(
        self,
        capabilities: list[PhysicalTxChannelCapability],
        cache_dir: Path,
        device: SoapyDevice | None = None,
        device_args: str = "",
        enable_real_tx: bool = False,
    ) -> None:
        super().__init__(
            capabilities=capabilities,
            cache_dir=cache_dir,
            device=device or _open_real_soapy_device(device_args),
            device_family="air7311",
            enable_real_tx=enable_real_tx,
        )
