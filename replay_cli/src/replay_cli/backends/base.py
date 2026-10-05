"""Common playback backend interface (CLAUDE.md: "Common interface:
`play(composite_meta, gain_db, repeat, arm)`").
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol


class ReplayBackend(Protocol):
    def play(self, composite_meta: Path, gain_db: float, repeat: int, arm: bool) -> None: ...
