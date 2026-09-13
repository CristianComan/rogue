"""ROGUE backend package.

RF Operations Generator for Unified Experimentation — control-plane API,
scenario/domain logic, RF Environment Compiler and orchestration code.

M0 scope: package exists so the FastAPI health-check shell can be
installed and imported as ``rogue``. Sub-packages for scenarios,
spectrum planning, replay, and hardware orchestration are added by their
corresponding milestones in docs/architecture/implementation-plan.md.
"""

__all__: list[str] = []
