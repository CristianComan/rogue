"""Run execution (M7): a vendor-neutral SDR adapter contract and a
first-class simulated implementation, plus the orchestration state machine
that drives a compiled ReplayPlan through prepare/arm/start/stop.

In-process only — no NATS, no separate Agent process. Wiring this same
orchestration to real, distributed Agent processes is M8's job (see
docs/architecture/implementation-plan.md and rogue.execution.__init__'s
sibling modules' docstrings for the exact scope boundary).
"""
