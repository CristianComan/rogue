"""SDRAgent runtime inventory (M8).

domain-model.md deliberately deferred `SDRAgent`/`SDRDevice`/
`PhysicalTxChannel` past M1 ("runtime/execution concerns ... belong to
M6+"). This is the M8 shape: a presence-driven record of which Agent
processes are alive and what they report they can do — not scenario data,
not versioned/immutable like `ScenarioVersion`. `status` is derived at read
time from how stale `last_seen_at` is, not stored, so there is nothing to
keep in sync with a heartbeat that simply stops arriving.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from enum import StrEnum

from pydantic import computed_field

from rogue.compiler.models import PhysicalTxChannelCapability
from rogue.domain.common import RogueModel

# An agent that hasn't heartbeated within this window is reported STALE
# rather than ONLINE (CLAUDE.md rule 10: runtime discovery is authoritative,
# so a stale record must say so rather than implying current capability).
PRESENCE_STALE_AFTER_SECONDS = 15.0


class AgentStatus(StrEnum):
    ONLINE = "online"
    STALE = "stale"


class SDRAgentRecord(RogueModel):
    """One Agent process's last-known presence and reported capabilities."""

    agent_id: str
    mode: str
    capabilities: list[PhysicalTxChannelCapability]
    last_seen_at: datetime

    @computed_field  # type: ignore[prop-decorator]
    @property
    def status(self) -> AgentStatus:
        age = datetime.now(UTC) - self.last_seen_at
        if age > timedelta(seconds=PRESENCE_STALE_AFTER_SECONDS):
            return AgentStatus.STALE
        return AgentStatus.ONLINE
