"""RF link, emission and frequency-behaviour domain entities.

Models the scenario-authored side of docs/architecture/rf-model.md:
DroneRfLink, RfBand, RfEmission, FrequencyBehaviour and FrequencyEvent.
RfWindow, CompositeChannel, PhysicalTxChannel, HardwareCapability and
Allocation are compiler/scheduler artifacts (RF Environment Compiler, M6)
and are intentionally not modelled here — per ADR-002 and CLAUDE.md rule 1,
scenarios never bind to a physical device/channel. ``ResourcePreference``
below is the only hardware-adjacent input a scenario may express, and it is
a non-binding preference, not an allocation.
"""

from __future__ import annotations

from datetime import timedelta
from enum import StrEnum

from pydantic import Field, field_validator, model_validator

from rogue.domain.common import IdentifiedMixin, RogueModel
from rogue.domain.recording import RecordingReference


class RfLinkRole(StrEnum):
    """Purpose of a logical drone RF link."""

    C2 = "c2"
    TELEMETRY = "telemetry"
    VIDEO = "video"
    DATA = "data"


class RfBand(RogueModel):
    """Allowed band/range and, optionally, an explicit channel plan."""

    freq_min_hz: float = Field(gt=0)
    freq_max_hz: float = Field(gt=0)
    allowed_channels_hz: list[float] = Field(default_factory=list)

    @model_validator(mode="after")
    def _range_and_channels_valid(self) -> RfBand:
        if self.freq_max_hz <= self.freq_min_hz:
            raise ValueError("freq_max_hz must be greater than freq_min_hz")
        for f in self.allowed_channels_hz:
            if not (self.freq_min_hz <= f <= self.freq_max_hz):
                raise ValueError(
                    f"channel {f} Hz falls outside [{self.freq_min_hz}, {self.freq_max_hz}]"
                )
        return self


class RfEmission(IdentifiedMixin):
    """A logical scheduled span on a DroneRfLink's timeline. Not a physical TX channel.

    ``recording`` is optional: ``None`` authors an explicit silence span (the
    link is deliberately off-air for this span), distinct from simply not
    scheduling anything there. A signal-of-interest vs. background-only span
    is not a separate flag here — it follows from the referenced recording's
    ``IQRecording.kind``.
    """

    recording: RecordingReference | None = None
    start_offset: timedelta = timedelta(0)
    duration_override: timedelta | None = None
    gain_offset_db: float = 0.0
    loop: bool = False
    notes: str | None = None

    @model_validator(mode="after")
    def _silence_requires_explicit_duration(self) -> RfEmission:
        if self.recording is None and self.duration_override is None:
            raise ValueError(
                "an emission with no recording (an explicit silence span) requires "
                "duration_override"
            )
        return self


class FrequencySwitchingMode(StrEnum):
    """How instantaneous frequency is determined over time."""

    SCRIPTED = "scripted"
    MISSION_TRIGGERED = "mission_triggered"
    PROBABILISTIC_ADAPTIVE = "probabilistic_adaptive"
    EXTERNAL_STATE_TRIGGERED = "external_state_triggered"


class FrequencyTransitionType(StrEnum):
    """rf-model.md section 3: intra-window vs. inter-window frequency moves."""

    CHANNEL_SWITCH = "channel_switch"
    BAND_SWITCH = "band_switch"


class ScriptedFrequencyChange(RogueModel):
    """One authored entry in a SCRIPTED frequency behaviour."""

    at_offset: timedelta
    frequency_hz: float = Field(gt=0)
    transition_type: FrequencyTransitionType = FrequencyTransitionType.CHANNEL_SWITCH


class FrequencyBehaviour(RogueModel):
    """Time-varying frequency behaviour rules for a DroneRfLink.

    Deterministic switching (scripted, mission-triggered) is fully
    specified here. Probabilistic/adaptive and external-triggered modes
    are scoped to the fields needed for determinism (a random seed and a
    trigger reference); the dwell-distribution/trigger-protocol detail is
    left to the spectrum planner (M5) and orchestration (M11) milestones.
    """

    mode: FrequencySwitchingMode
    scripted_changes: list[ScriptedFrequencyChange] = Field(default_factory=list)
    mission_trigger_anchor: str | None = None
    random_seed: int | None = None
    mean_dwell_s: float | None = None
    external_trigger_reference: str | None = None

    @model_validator(mode="after")
    def _fields_match_mode(self) -> FrequencyBehaviour:
        if self.mode == FrequencySwitchingMode.SCRIPTED and not self.scripted_changes:
            raise ValueError("SCRIPTED mode requires at least one scripted_changes entry")
        is_mission_triggered = self.mode == FrequencySwitchingMode.MISSION_TRIGGERED
        if is_mission_triggered and not self.mission_trigger_anchor:
            raise ValueError("MISSION_TRIGGERED mode requires mission_trigger_anchor")
        if self.mode == FrequencySwitchingMode.PROBABILISTIC_ADAPTIVE and self.random_seed is None:
            raise ValueError("PROBABILISTIC_ADAPTIVE mode requires a random_seed for repeatability")
        if (
            self.mode == FrequencySwitchingMode.EXTERNAL_STATE_TRIGGERED
            and not self.external_trigger_reference
        ):
            raise ValueError("EXTERNAL_STATE_TRIGGERED mode requires external_trigger_reference")
        return self


class FrequencyEvent(IdentifiedMixin):
    """A realized (or worked-example) channel/band change with reason.

    Authored scenarios may include worked examples for validation/preview;
    the authoritative realized sequence for a run is produced by the RF
    Environment Compiler and recorded in the Replay Plan (M6), not here.
    """

    transition_type: FrequencyTransitionType
    at_offset: timedelta
    frequency_hz: float = Field(gt=0)
    reason: str
    seed_context: int | None = None


class TimingSyncClass(StrEnum):
    """sdr-architecture.md section 5 synchronization classes."""

    L0_SIMULATED = "l0_simulated"
    L1_SOFTWARE_BARRIER = "l1_software_barrier"
    L2_SCHEDULED_LOCAL = "l2_scheduled_local"
    L3_SHARED_REFERENCE = "l3_shared_reference"
    L4_MEASURED = "l4_measured"


class ResourcePreference(RogueModel):
    """Non-binding capability preference. Never a device/channel binding.

    Deliberately excludes any device serial, agent identity or channel
    index field — CLAUDE.md rule 1 and ADR-002 require canonical scenarios
    to stay hardware-independent. Actual allocation happens during run
    preparation and is recorded only in the immutable run manifest.
    """

    preferred_agent_tags: list[str] = Field(default_factory=list)
    required_sync_class: TimingSyncClass | None = None
    notes: str | None = None


class DroneRfLink(IdentifiedMixin):
    """A logical RF relationship owned by a drone mission (C2, telemetry, ...)."""

    role: RfLinkRole
    band: RfBand
    frequency_behaviour: FrequencyBehaviour
    emissions: list[RfEmission] = Field(default_factory=list)
    resource_preference: ResourcePreference | None = None

    @field_validator("emissions")
    @classmethod
    def _at_least_one_emission(cls, value: list[RfEmission]) -> list[RfEmission]:
        if not value:
            raise ValueError("a DroneRfLink requires at least one RfEmission")
        return value
