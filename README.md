# ROGUE Design Documentation

**ROGUE — RF Operations Generator for Unified Experimentation**

This documentation set decomposes the ROGUE System Design baseline v0.3 (20 August 2026) into implementation-oriented architecture documents for use by the development team and Claude Code.

## Scope

ROGUE is a scenario-driven Hardware-in-the-Loop platform for generating controlled, repeatable and realistic RF environments from SigMF I/Q recordings for Electronic Support experimentation and receiver evaluation.

In scope:
- scenario-driven replay and HIL execution;
- Electronic Support stimulation;
- spectrum planning, frequency assignment and deconfliction;
- receiver geometry and propagation effects;
- SigMF recording management and replay;
- independent RF validation and monitoring.

Out of scope: Electronic Attack, operational C2, sensor fusion, autonomous engagement, and replacement of ESM/C2/drone-autopilot systems.

## Documentation map

- `docs/architecture/system-design.md` — system context, requirements, components, workflows, run lifecycle and deployment.
- `docs/architecture/domain-model.md` — canonical scenario/domain entities, invariants, versioning and timeline semantics.
- `docs/architecture/rf-model.md` — RF links, frequency behaviour, spectrum planning, composite replay, receiver effects and Replay Plan.
- `docs/architecture/sdr-architecture.md` — SDR Agent, hardware abstraction, initial X440/AIR7311 pool, timing and safety.
- `docs/architecture/verification-validation.md` — software, HIL and independent RF validation strategy.
- `docs/architecture/implementation-plan.md` — phased implementation and Claude-sized work packages.
- `docs/decisions/ADR-001-replay-plan.md` — Scenario → Replay Plan → SDR Agents boundary.
- `docs/decisions/ADR-002-hardware-independent-scenarios.md` — no canonical scenario-to-device binding.
- `docs/decisions/ADR-003-composite-rf-windows.md` — physical TX channels as wideband RF windows.
- `CLAUDE.md` — mandatory development instructions for Claude Code.

## Development principle

> Architecture first, small features second, hardware integration last.

The scenario expresses **what RF environment should exist**. The RF Environment Compiler produces an immutable **Replay Plan** describing exactly how available physical resources will realize it. SDR Agents execute that plan through vendor-specific adapters.
