"""SQLAlchemy persistence wiring for the ROGUE control-plane API.

Engine/session setup and ORM models. Domain <-> ORM translation lives in
``rogue.persistence.repository``, not here — this package only knows about
tables and columns.
"""

from __future__ import annotations

__all__: list[str] = []
