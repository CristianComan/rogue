"""Domain <-> ORM translation and query/write operations for scenarios.

Nothing outside ``rogue.persistence`` should import ``rogue.db`` directly —
callers (the API layer) work only with ``rogue.domain`` models and the
functions/exceptions exported here.
"""

from __future__ import annotations

__all__: list[str] = []
