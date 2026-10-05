"""Catalog and scenario schema for the SigMF drone replay tool.

Source of truth for: variant names, geometry->variant rule table, radio limits,
scenario and catalog models, and event resolution.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

import yaml
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


# --------------------------------------------------------------------------
# Variants and geometry rule
# --------------------------------------------------------------------------
class Variant(str, Enum):
    DRONE = "drone"
    CONTROLLER = "controller"
    BOTH = "both"


class Side(str, Enum):
    DRONE = "drone"
    CONTROLLER = "controller"


# Observer geometry -> recording to replay (as recorded, no attenuation).
RULE_TABLE: dict[frozenset[Side], Variant | None] = {
    frozenset({Side.DRONE}): Variant.DRONE,
    frozenset({Side.CONTROLLER}): Variant.CONTROLLER,
    frozenset({Side.DRONE, Side.CONTROLLER}): Variant.BOTH,
    frozenset(): None,  # near neither: nothing visible
}


def resolve_variant(near: list[Side]) -> Variant | None:
    return RULE_TABLE[frozenset(near)]


# --------------------------------------------------------------------------
# Radios
# --------------------------------------------------------------------------
class RadioType(str, Enum):
    AIRT7311 = "airt7311"
    AIRT7201 = "airt7201"
    X440 = "x440"


class RadioLimits(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    f_min_mhz: float
    f_max_mhz: float
    max_bw_mhz: float
    max_rate_msps: float
    max_tx_power_dbm: float | None = None


RADIO_LIMITS: dict[RadioType, RadioLimits] = {
    # From Deepwave docs (AD9371): 300 MHz-6 GHz, 100 MHz BW, 125 MSPS, +20 dBm
    RadioType.AIRT7311: RadioLimits(
        f_min_mhz=300, f_max_mhz=6000, max_bw_mhz=100, max_rate_msps=125, max_tx_power_dbm=20
    ),
    RadioType.AIRT7201: RadioLimits(
        f_min_mhz=300, f_max_mhz=6000, max_bw_mhz=100, max_rate_msps=125, max_tx_power_dbm=20
    ),
    # Ettus X440 (kb.ettus.com/X440): direct sampling, 30 MHz-4 GHz (tunable
    # down to 1 MHz), NO RF above 4 GHz without an external upconverter, so
    # 5.8 GHz signals cannot be replayed on it directly. IBW is up to 1600 MHz
    # on 2 channels but 400 MHz on 8 channels; we use the conservative 8-ch
    # figure (X440_X4_400 image). Raise for a 2-ch/1600 MHz FPGA image.
    # Max output about 0 dBm (varies with master clock rate and frequency).
    # max_rate_msps is the IQ rate and depends on image/master clock: VERIFY.
    RadioType.X440: RadioLimits(
        f_min_mhz=30, f_max_mhz=4000, max_bw_mhz=400, max_rate_msps=500, max_tx_power_dbm=0
    ),
}


class RadioSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: RadioType
    channel: int = Field(0, ge=0)
    center_mhz: float
    rate_msps: float = Field(gt=0)
    tx_gain_db: float
    # Mandatory on purpose: forces a conscious per-scenario safety cap.
    # Units are radio-native; calibrate conducted before choosing values.
    max_tx_gain_db: float
    device_args: str | None = None  # e.g. "driver=SoapyAIRT" or UHD args

    @property
    def limits(self) -> RadioLimits:
        return RADIO_LIMITS[self.type]

    @model_validator(mode="after")
    def _check_limits(self) -> RadioSpec:
        lim = self.limits
        if not (lim.f_min_mhz <= self.center_mhz <= lim.f_max_mhz):
            raise ValueError(
                f"center_mhz {self.center_mhz} outside "
                f"{lim.f_min_mhz}-{lim.f_max_mhz} MHz for {self.type.value}"
            )
        if self.rate_msps > lim.max_rate_msps:
            raise ValueError(
                f"rate_msps {self.rate_msps} exceeds {lim.max_rate_msps} for {self.type.value}"
            )
        if self.tx_gain_db > self.max_tx_gain_db:
            raise ValueError(
                f"tx_gain_db {self.tx_gain_db} exceeds max_tx_gain_db {self.max_tx_gain_db}"
            )
        return self

    @property
    def usable_bw_mhz(self) -> float:
        return min(self.rate_msps, self.limits.max_bw_mhz)


# --------------------------------------------------------------------------
# Scenario
# --------------------------------------------------------------------------
class NoisePolicy(str, Enum):
    KEEP = "keep"  # leave recorded noise floor (realistic)
    TRIM_BURSTS = "trim_bursts"  # gate to active bursts (lower summed floor)


class Event(BaseModel):
    model_config = ConfigDict(extra="forbid")

    drone: str
    near: list[Side] = Field(default_factory=list)
    use: Variant | None = None  # explicit override of the rule table
    start_s: float = Field(0.0, ge=0)
    dur_s: float = Field(gt=0)
    loop: bool = False
    gain_db: float = 0.0  # level balancing only

    @field_validator("near")
    @classmethod
    def _dedupe(cls, v: list[Side]) -> list[Side]:
        return list(dict.fromkeys(v))

    @property
    def variant(self) -> Variant | None:
        return self.use if self.use is not None else resolve_variant(self.near)

    @property
    def end_s(self) -> float:
        return self.start_s + self.dur_s

    @property
    def reason(self) -> str:
        if self.use is not None:
            note = " (near ignored)" if self.near else ""
            return f"explicit use: {self.use.value}{note}"
        if not self.near:
            return "near neither emitter -> nothing visible, event skipped"
        sides = " + ".join(s.value for s in self.near)
        variant = self.variant
        assert variant is not None  # RULE_TABLE only maps the empty set to None, excluded above
        return f"near {sides} -> {variant.value}"


class Scenario(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(pattern=r"^[A-Za-z0-9_\-]+$")
    description: str = ""
    radio: RadioSpec
    events: list[Event] = Field(min_length=1)
    noise_policy: NoisePolicy = NoisePolicy.KEEP
    headroom_dbfs: float = Field(-3.0, le=0.0)  # composite peak target

    @property
    def duration_s(self) -> float:
        return max(e.end_s for e in self.events)

    @classmethod
    def load(cls, path: str | Path) -> Scenario:
        with open(path, encoding="utf-8") as f:
            return cls.model_validate(yaml.safe_load(f))


# --------------------------------------------------------------------------
# Catalog
# --------------------------------------------------------------------------
class CatalogError(Exception):
    pass


class Recording(BaseModel):
    model_config = ConfigDict(extra="forbid")

    meta: Path
    # Filled in by the scanner from the .sigmf-meta:
    data: Path | None = None
    datatype: str | None = None  # core:datatype, e.g. cf32_le
    sample_rate_hz: float | None = None  # core:sample_rate
    center_freq_hz: float | None = None  # captures[0] core:frequency
    duration_s: float | None = None


class DroneEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    variants: dict[Variant, Recording]
    notes: str = ""

    @property
    def missing_variants(self) -> list[Variant]:
        return [v for v in Variant if v not in self.variants]


class Catalog(BaseModel):
    model_config = ConfigDict(extra="forbid")

    drones: dict[str, DroneEntry]

    @classmethod
    def load(cls, path: str | Path) -> Catalog:
        with open(path, encoding="utf-8") as f:
            raw = yaml.safe_load(f)
        return cls(drones=raw)

    def get(self, drone: str, variant: Variant) -> Recording:
        if drone not in self.drones:
            raise CatalogError(f"unknown drone '{drone}'")
        entry = self.drones[drone]
        if variant not in entry.variants:
            raise CatalogError(f"drone '{drone}' has no '{variant.value}' recording")
        return entry.variants[variant]


# --------------------------------------------------------------------------
# Resolution (scenario + catalog -> concrete recordings)
# --------------------------------------------------------------------------
@dataclass
class ResolvedEvent:
    event: Event
    variant: Variant | None
    recording: Recording | None
    reason: str

    @property
    def skipped(self) -> bool:
        return self.variant is None


def resolve_events(scenario: Scenario, catalog: Catalog) -> list[ResolvedEvent]:
    """Map every event to a recording. Raises CatalogError on missing data."""
    out: list[ResolvedEvent] = []
    for ev in scenario.events:
        v = ev.variant
        rec = catalog.get(ev.drone, v) if v is not None else None
        out.append(ResolvedEvent(ev, v, rec, ev.reason))
    return out
