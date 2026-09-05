"""NATS subject naming (sdr-architecture.md §4).

Command/reply is one subject per agent so NATS itself routes/queues per
agent rather than every Agent process filtering a shared subject by
`agent_id` in the payload. Presence keeps the single shared subject the M0
placeholder (`agents/common/main.py`) already publishes on.
"""

from __future__ import annotations

PRESENCE_SUBJECT = "rogue.agents.presence"


def agent_command_subject(agent_id: str) -> str:
    return f"rogue.agents.{agent_id}.cmd"


def agent_telemetry_subject(agent_id: str) -> str:
    return f"rogue.agents.{agent_id}.telemetry"
