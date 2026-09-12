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
from uuid import UUID

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


class ZoneTriggerPolicy(RogueModel):
    """Derives an ``RfEmission``'s active span from a scenario ``Zone``
    instead of ``start_offset``/``duration_override`` (region simulation
    semantics, ADR-015): the emission is active for exactly the sub-
    intervals its mission's trajectory is inside ``zone_id``'s polygon,
    computed by ``rogue.domain.mission_evaluator.zone_crossings``.
    Reference integrity (``zone_id`` must resolve to a ``TRIGGER``-typed
    ``Zone`` in the same ``ScenarioVersion``) is a cross-entity concern,
    checked by ``rogue.domain.validation.validate_scenario_version``, not
    here — this field alone doesn't know the scenario's zones.
    """

    zone_id: UUID


class RfEmission(IdentifiedMixin):
    """A logical scheduled span on a DroneRfLink's timeline. Not a physical TX channel.

    ``recording`` is optional: ``None`` authors an explicit silence span (the
    link is deliberately off-air for this span), distinct from simply not
    scheduling anything there. A signal-of-interest vs. background-only span
    is not a separate flag here — it follows from the referenced recording's
    ``IQRecording.kind``.

    ``zone_trigger``, when set, replaces ``start_offset``/``duration_override``
    as the source of this emission's active span entirely (mutually
    exclusive — see the validator below): a "trigger region" scenario, where
    entering/leaving a zone starts/stops the signal, rather than an authored
    fixed time window.
    """

    recording: RecordingReference | None = None
    start_offset: timedelta = timedelta(0)
    duration_override: timedelta | None = None
    zone_trigger: ZoneTriggerPolicy | None = None
    gain_offset_db: float = 0.0
    loop: bool = False
    notes: str | None = None

    @model_validator(mode="after")
    def _silence_requires_explicit_duration(self) -> RfEmission:
        if self.recording is None and self.duration_override is None and self.zone_trigger is None:
            raise ValueError(
                "an emission with no recording (an explicit silence span) requires "
                "duration_override"
            )
        return self

    @model_validator(mode="after")
    def _zone_trigger_excludes_manual_timing(self) -> RfEmission:
        if self.zone_trigger is None:
            return self
        if self.recording is None:
            raise ValueError("a zone-triggered emission requires a recording")
        if self.duration_override is not None:
            raise ValueError(
                "a zone-triggered emission's duration is derived from zone crossings, not "
                "duration_override"
            )
        if self.start_offset != timedelta(0):
            raise ValueError(
                "a zone-triggered emission's start is derived from zone crossings, not "
                "start_offset"
            )
        if self.loop:
            raise ValueError("a zone-triggered emission cannot also loop")
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

    # Declares that this link's emission must be coherently synthesized
    # (matching Δφ/τ per rf-model.md section 6) across every Receiver
    # sharing this array_group_id — i.e. Receiver.array_group_id, not a new
    # identifier space. Reference-integrity (the group must resolve to >=2
    # TDOA/AOA_DOA receivers) is a cross-entity concern, checked by
    # rogue.domain.validation.validate_scenario_version, not here — this
    # field alone doesn't know the scenario's receivers.
    array_group_id: UUID | None = None

    # Which single MONITOR receiver, if any, "hears" this link's emissions
    # (region/receiver simulation semantics, ADR-015) — orthogonal to
    # array_group_id above (TDOA/AOA_DOA coherent groups): purely
    # informational for now (intended for a future planning sync matrix /
    # run channel display), never changing channel count or allocation
    # (unlike array_group_id). rogue.compiler.models.CompositeChannel does
    # not carry this through yet — that's unbuilt follow-up work, not
    # claimed here. A link with no receiver at all is simply replayed with
    # no geometry applied — this field is optional and independent of that.
    # Reference integrity (must resolve to a MONITOR-type Receiver) is
    # checked by rogue.domain.validation.validate_scenario_version,
    # mirroring array_group_id's own precedent.
    observed_by_receiver_id: UUID | None = None

    @field_validator("emissions")
    @classmethod
    def _at_least_one_emission(cls, value: list[RfEmission]) -> list[RfEmission]:
        if not value:
            raise ValueError("a DroneRfLink requires at least one RfEmission")
        return value
