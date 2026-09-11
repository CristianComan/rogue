"""Independent RF validation (M14): capture, compare, and attach evidence.

See docs/architecture/implementation-plan.md's M14 entry, rf-model.md
section 9 and verification-validation.md section 4. This package is
deliberately independent of ``rogue.execution`` (the replay command path,
CLAUDE.md rule 15): ``monitor_adapter.RfMonitorAdapter`` shares no code or
state with ``rogue.execution.adapter.SDRAdapter``.
"""

from __future__ import annotations
