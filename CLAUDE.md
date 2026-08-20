# ROGUE Development Instructions for Claude

## 1. Project identity

ROGUE (RF Operations Generator for Unified Experimentation) is a distributed scenario-driven Hardware-in-the-Loop platform for generating controlled, repeatable RF environments from SigMF I/Q recordings for Electronic Support experimentation and receiver evaluation.

Read `README.md` and all relevant files under `docs/architecture/` and `docs/decisions/` before proposing or implementing changes.

## 2. Scope guardrails

ROGUE includes:
- scenario authoring/versioning;
- drone missions and deterministic trajectory playback;
- SigMF catalogue/replay;
- RF spectrum planning and deconfliction;
- frequency-agile logical RF links;
- RF Environment Compiler and Replay Plan;
- receiver geometry/effects for monitoring, TDOA and AOA/DOA;
- distributed SDR Agents and vendor adapters;
- run orchestration, evidence and independent RF validation.

Do not expand ROGUE into Electronic Attack, operational C2, sensor fusion, autonomous engagement, or a replacement ESM/drone-autopilot system unless an explicit new requirement changes the approved scope.

## 3. Non-negotiable architecture rules

1. **Scenarios are hardware-independent.** Never bind a drone or canonical RF link directly to a specific SDR/device/channel.
2. **Scenario and execution are separated by a Replay Plan.** Scenario = desired RF environment; Replay Plan = exact executable resource/DSP/timing allocation.
3. **Vendor drivers remain behind SDR adapters.** No UHD/Soapy/libiio/vendor-specific assumptions in scenario/domain services.
4. **Physical TX channels are RF windows.** Multiple logical emissions may share one wideband channel.
5. **Intentional overlap is legal.** Do not reject overlap by default; assess feasibility, bandwidth, headroom, aggregate power and policy.
6. **Frequency agility is first-class.** Distinguish `CHANNEL_SWITCH` inside an RF window from `BAND_SWITCH` requiring scheduler reevaluation/migration.
7. **SigMF is the native recording format.** Preserve unknown extension metadata. Do not modify source recordings during ingest/preview.
8. **Large I/Q data is not stored in Git and is not routed through the control plane.** Prefetch to SDR-node cache and stream locally with bounded buffers.
9. **Receiver geometry is scenario data.** Support `MONITOR`, `TDOA`, and `AOA_DOA` with explicit delay/phase relationships.
10. **Runtime hardware discovery is authoritative.** Static X440/AIR7311 profiles are defaults only.
11. **Run manifests and published scenario versions are immutable.** Preserve hashes, realized random/frequency events, allocations and evidence.
12. **Safety is enforced centrally and locally.** Default deny TX; leases, expiry, watchdog and emergency stop are mandatory.
13. **Simulation comes before hardware.** New orchestration features must be testable with simulated agents.
14. **Determinism matters.** Mission/RF state must be computable from scenario time and fixed seeds, independent of UI frame rate.
15. **Independent RF validation is not the replay path.** Measurement/validation evidence must be compared against the compiled plan.

## 4. Initial hardware assumptions

Initial planning profile:
- 2 × Ettus USRP X440, 8 TX channels per unit;
- 2 × Deepwave AIR7311, 4 TX channels per unit;
- 24 planned physical TX channels total.

Trust runtime capability readback over these numbers.

Do not allocate 5.2/5.8 GHz to a native X440 RF path unless an explicit modeled frequency-conversion chain makes that path capable. AIR7311-capable paths are the normal initial choice for those bands.

## 5. Baseline technology

- Frontend: React + TypeScript + Vite + MapLibre GL JS; Vitest/Playwright.
- Backend: Python 3.12 + FastAPI + Pydantic v2 + SQLAlchemy 2 + Alembic.
- Database: PostgreSQL + PostGIS.
- Object storage: S3-compatible MinIO.
- Broker: NATS JetStream.
- Agent: Python service/package with simulated and real SDR adapters.
- Development: Docker Compose, Ruff, mypy, pytest, pre-commit, GitHub Actions.

Do not replace the baseline stack without first writing a proposal/ADR and obtaining approval.

## 6. Repository boundaries

Expected top-level structure:

```text
backend/        control-plane/domain/application code
frontend/       web UI
agents/         SDR Agent and adapter packages
schemas/        shared versioned contracts
examples/       small scenario and synthetic SigMF fixtures only
tests/          unit/integration/HIL tests
docs/           architecture, ADRs, API and engineering documentation
scripts/        developer/operations helpers
```

Keep UI, domain logic, compiler/DSP logic, orchestration and hardware adapters separate. API routes must not contain business logic.

## 7. Development protocol

Before editing files for any non-trivial task:
1. inspect the existing repository and relevant architecture/ADR documents;
2. restate the requirement and scope;
3. identify affected components/files/contracts;
4. identify invariants and compatibility impact;
5. propose tests;
6. for architectural/schema changes, present the plan before implementation.

Then implement incrementally.

Do not perform unrelated refactoring. Do not silently change public schemas or architectural boundaries.

## 8. Git rules

- Never commit directly to `main`.
- Use focused feature branches such as `feature/scenario-domain-model`.
- Keep commits small and coherent.
- Do not commit secrets, `.env` credentials, VPN keys, device credentials, large captures, `*.sigmf-data`, `*.iq`, `*.raw` or generated runtime artifacts.
- Do not force-push shared branches unless explicitly instructed.

## 9. Coding rules

- Prefer typed models and explicit interfaces/protocols.
- Use UTC timestamps and UUIDs where defined by the architecture.
- Use version fields for portable schemas/protocols.
- Preserve idempotency and correlation IDs for mutating/distributed operations.
- Use deterministic pure functions for mission and spectrum state where practical.
- Use bounded streaming buffers for I/Q processing; never load complete large recordings into RAM.
- Use numerically stable NCO/phase accumulation.
- Treat warnings vs blocking validation findings explicitly.
- Record assumptions; do not hide them in code.
- Add an ADR for significant architectural decisions.

## 10. Safety rules for code and tests

- Automated tests default to simulation or cabled/attenuated laboratory mode.
- Never enable uncontrolled over-the-air TX automatically.
- Real TX requires an explicit environment/configuration gate and approved policy.
- Hardware adapter code must stop on lease expiry/watchdog/control loss where supported.
- Emergency stop paths receive dedicated tests.

## 11. Required checks

For changed components, run the applicable:
- formatter/linter;
- static type checker;
- unit tests;
- contract/API tests;
- integration tests;
- hardware-marked tests only when explicitly enabled and safe.

Do not claim success if checks were not run. Report exact commands and results.

## 12. Completion report

At the end of an implementation task report:
- summary of implementation;
- files changed;
- schema/API/ADR impact;
- tests/checks executed and results;
- assumptions;
- unresolved risks or follow-up issues.

## 13. First development priority

Unless explicitly reprioritized, implement in this order:

```text
repository/foundations
-> scenario domain model
-> scenario persistence/API
-> map/mission engine
-> SigMF catalogue
-> spectrum planner
-> Replay Plan compiler
-> simulated SDR execution
-> distributed SDR Agent
-> real SDR adapters
-> synchronized multi-SDR replay
-> Doppler/delay/phase
-> TDOA/AOA receiver stimulation
-> independent RF validation
```

Do not jump directly to X440/AIR7311 implementation before the domain model, Replay Plan contract and simulated adapter boundaries are stable.
