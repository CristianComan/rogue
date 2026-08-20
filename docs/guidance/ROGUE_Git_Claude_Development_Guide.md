# ROGUE Git Repository Setup and Claude Development Guide

## 1. Purpose

This document provides a recommended approach for setting up the Git
repository and starting AI-assisted development of **ROGUE**, the
scenario-driven Hardware-in-the-Loop (HIL) RF/IQ replay environment.

The objective is to establish a controlled development process in which
the architecture, scenario model, RF model, and hardware abstractions
are defined before substantial code is generated.

ROGUE should be developed incrementally, with Claude working on small,
well-defined features rather than attempting to generate the complete
HIL application at once.

------------------------------------------------------------------------

## 2. Create the Git Repository

Assuming the GitHub repository `CristianComan/rogue` already exists and
is empty:

``` bash
mkdir rogue
cd rogue

git init
git branch -M main

cat > README.md <<'EOF'
# ROGUE

RF Orchestration and Generation environment for scenario-driven
IQ replay and hardware-in-the-loop C-UAS / EW testing.
EOF

git add README.md
git commit -m "Initial repository"

git remote add origin https://github.com/CristianComan/rogue.git
git push -u origin main
```

The GitHub URL in the terminal must be a plain URL, not Markdown syntax.

Verify the repository configuration:

``` bash
git remote -v
git status
git log --oneline
```

### Development Branch

Do not perform routine development directly on `main`.

Create a development branch:

``` bash
git checkout -b develop
git push -u origin develop
```

Individual development tasks can then use feature branches such as:

``` text
feature/scenario-model
feature/sigmf-library
feature/map-ui
feature/rf-planner
feature/sdr-agent
feature/orchestrator
feature/replay-engine
```

A typical workflow becomes:

``` text
feature branch
      |
      v
Pull Request
      |
      v
develop
      |
      v
integration / HIL testing
      |
      v
main
```

This is particularly useful when using an AI coding agent because
changes remain isolated and reviewable.

------------------------------------------------------------------------

## 3. Recommended Repository Structure

A suitable initial repository structure is:

``` text
rogue/
├── README.md
├── CLAUDE.md
├── LICENSE
├── .gitignore
├── pyproject.toml
├── docker-compose.yml
│
├── docs/
│   ├── architecture/
│   │   ├── system-design.md
│   │   ├── domain-model.md
│   │   ├── rf-model.md
│   │   └── sdr-architecture.md
│   ├── api/
│   └── decisions/
│
├── backend/
│   └── rogue/
│       ├── api/
│       ├── scenarios/
│       ├── spectrum/
│       ├── signals/
│       ├── receivers/
│       ├── propagation/
│       ├── orchestration/
│       ├── replay/
│       ├── hardware/
│       └── common/
│
├── frontend/
│   ├── src/
│   └── tests/
│
├── agents/
│   ├── common/
│   ├── ettus/
│   └── deepwave/
│
├── schemas/
│   ├── scenario/
│   ├── signal/
│   ├── receiver/
│   └── hardware/
│
├── examples/
│   ├── scenarios/
│   └── sigmf/
│
├── tests/
│   ├── unit/
│   ├── integration/
│   └── hil/
│
├── scripts/
│
└── .github/
    └── workflows/
```

------------------------------------------------------------------------

## 4. Architectural Separation

One of the most important design rules is:

> **The scenario definition must not know how an Ettus X440 or Deepwave
> AIR7311 works.**

The architecture should maintain the following separation:

``` text
Scenario Model
      |
      v
RF / Propagation Model
      |
      v
Replay Plan
      |
      v
Hardware-Independent Orchestration
      |
      +------> Ettus Adapter / Agent
      |
      +------> Deepwave Adapter / Agent
```

This separation becomes essential when signals are dynamically assigned
across multiple SDR channels and frequency bands.

ROGUE must support frequency-agile emitters operating in bands such as:

-   2.4 GHz
-   5.2 GHz
-   5.8 GHz

Signals may overlap or operate at slightly different frequencies within
the same band, as occurs with real drone systems searching for less
congested spectrum.

------------------------------------------------------------------------

## 5. Add the ROGUE Architecture Documentation

Place the ROGUE design documentation under:

``` text
docs/architecture/
```

Recommended initial documents are:

``` text
docs/architecture/system-design.md
docs/architecture/domain-model.md
docs/architecture/rf-model.md
docs/architecture/sdr-architecture.md
```

Architectural decisions that arise during implementation should be
recorded separately:

``` text
docs/decisions/
```

For example:

``` text
ADR-001-replay-plan.md
ADR-002-sdr-agent-interface.md
ADR-003-scenario-versioning.md
```

This prevents important decisions from existing only inside Claude
conversations.

------------------------------------------------------------------------

## 6. Create `CLAUDE.md`

Create a `CLAUDE.md` file at the repository root.

This gives Claude persistent project-level instructions.

A suitable starting version is:

``` markdown
# ROGUE Development Instructions

## Project

ROGUE is a distributed hardware-in-the-loop RF scenario generation
and IQ replay platform.

Its primary purpose is scenario-driven replay of recorded baseband IQ
signals through multiple network-connected SDRs.

## Key Architectural Principles

1. Scenario definitions are hardware-independent.
2. SDR-specific functionality is isolated behind hardware adapters.
3. Scenario planning and scenario execution are separate operations.
4. Every scenario must be completely serializable and reproducible.
5. Replay must support multiple simultaneous signals.
6. Signals may share the same RF band and may partially overlap.
7. Frequency allocation is dynamic and scenario controlled.
8. Drone emitters may change frequency during a scenario.
9. Supported initial RF bands include 2.4 GHz, 5.2 GHz and 5.8 GHz.
10. Signal files use SigMF wherever practical.
11. Timing, frequency, amplitude, Doppler, delay and phase are explicit
    scenario parameters.
12. Receiver models include:
    - single-channel monitoring
    - TDOA
    - AOA/DOA
13. Hardware control must initially support:
    - Ettus X440
    - Deepwave AIR7311
14. No SDR-specific assumptions are allowed in the scenario domain model.
15. RF output must eventually support independent monitoring/validation.

## Development Rules

- Do not perform major architectural refactoring without proposing it first.
- Prefer small, testable modules.
- Add tests for new domain logic.
- Do not mix UI, domain logic and hardware-control code.
- Do not create mock RF behavior inside production hardware adapters.
- Use typed models for all scenario entities.
- Configuration must not contain secrets.
- Do not silently change public schemas.
- Document architectural decisions in docs/decisions/.
- Before implementing a feature:
  1. inspect the relevant architecture;
  2. describe the proposed change;
  3. identify files to change;
  4. identify tests;
  5. then implement.

## Git

Never commit directly to main.

Use feature branches and focused commits.

Do not commit generated IQ recordings, large binary recordings,
credentials, API keys or hardware-specific secrets.
```

The purpose of this file is to make Claude operate within the ROGUE
architecture instead of independently inventing a new architecture
during each development session.

------------------------------------------------------------------------

## 7. Do Not Store IQ Recordings in Git

Real SigMF recordings can rapidly reach hundreds of megabytes or
gigabytes.

Git should therefore contain only small synthetic/test recordings.

For example:

``` text
examples/sigmf/
```

may contain minimal test vectors required for automated tests.

Actual recordings should live outside the Git repository, for example:

``` text
/data/rogue/library/
```

or on a NAS/object store.

The scenario should reference the recording logically:

``` yaml
signal:
  id: dji-air3s-control-001
  dataset: sigmf://library/dji/air3s/control-001
  sample_rate: 61440000
  center_frequency: 0
```

The repository stores the scenario and metadata, while the large IQ data
remains external.

------------------------------------------------------------------------

## 8. Recommended `.gitignore`

Create a `.gitignore` similar to:

``` gitignore
# Python
__pycache__/
*.pyc
.venv/
.pytest_cache/
.mypy_cache/

# JavaScript
node_modules/
dist/
build/

# IDE
.vscode/
.idea/

# Environment / secrets
.env
.env.*
!.env.example

# Logs
*.log
logs/

# Runtime
runtime/
tmp/

# IQ / RF data
*.sigmf-data
*.iq
*.bin
*.raw

# Large captures
captures/
recordings/
datasets/
```

A `.sigmf-meta` file may sometimes be appropriate to version, while the
corresponding `.sigmf-data` file generally should not be committed.

------------------------------------------------------------------------

## 9. Start Claude Development in Analysis/Plan Mode

From inside the repository:

``` bash
cd rogue
claude
```

The first Claude session should **not generate code**.

Ask Claude to first understand the architecture.

Suggested initial prompt:

``` text
Read README.md, CLAUDE.md and everything under docs/architecture/.

Do not modify any files.

Explain your understanding of ROGUE in terms of:

1. domain model
2. scenario lifecycle
3. RF signal lifecycle
4. hardware abstraction
5. distributed SDR orchestration
6. receiver simulation
7. proposed backend/frontend boundaries

Identify ambiguities and architectural risks.

Do not implement anything yet.
```

When available, Claude can also be started in plan mode:

``` bash
claude --permission-mode plan
```

The objective of this stage is to verify that Claude understands the
architecture before it starts generating implementation code.

------------------------------------------------------------------------

## 10. First Implementation Milestone: Scenario Definition MVP

Do not initially implement:

-   SDR control;
-   GNU Radio processing;
-   X440 integration;
-   AIR7311 integration;
-   live IQ replay.

The first milestone should prove that ROGUE can accurately describe a
scenario.

A conceptual scenario model could be:

``` text
Scenario
 ├── Environment
 ├── Timeline
 ├── Emitters
 │    └── Drone
 │         ├── Trajectory
 │         └── RF Emissions
 │              ├── Signal Recording
 │              ├── Band
 │              ├── Frequency
 │              ├── Bandwidth
 │              ├── Power
 │              └── Frequency Transitions
 │
 ├── Receivers
 │    ├── Monitoring
 │    ├── TDOA
 │    └── AOA
 │
 └── Hardware Resources
```

Frequency agility must be a property of the scenario.

For example:

``` text
00:00   Start mission
00:10   2.437 GHz
00:25   2.462 GHz
00:42   Switch to 5.765 GHz
01:20   5.805 GHz
02:00   Mission end
```

This is important because frequency behavior belongs to the simulated
emitter, not to a specific SDR implementation.

------------------------------------------------------------------------

## 11. First Claude Implementation Prompt

After Claude has reviewed the architecture, create a feature branch:

``` bash
git checkout develop
git pull
git checkout -b feature/scenario-domain-model
```

Then use a tightly scoped implementation prompt such as:

``` text
Create/operate on the feature branch feature/scenario-domain-model.

Implement only the ROGUE scenario domain model.

Do not implement SDR control, RF replay, propagation processing,
frontend functionality or database persistence.

Requirements:

- Python backend
- strongly typed models
- Pydantic models where appropriate
- YAML and JSON serialization
- schema versioning
- deterministic scenario identifiers where appropriate

Implement entities for:

- Scenario
- Timeline
- Platform
- Drone
- Trajectory
- Waypoint
- RFEmitter
- RFEmission
- SignalRecording
- FrequencyBand
- FrequencyEvent
- Receiver
- MonitoringReceiver
- TDOAReceiver
- AOAReceiver
- SDRResource

RF emissions must support frequency changes during execution.

A drone may have multiple RF emissions.

Several emissions may occupy overlapping frequency ranges.

Do not prevent overlaps in the domain model; spectrum conflict
analysis belongs to a separate planner.

Create:

- models
- validation
- JSON schemas
- YAML examples
- unit tests
- documentation

Before editing files, show me:

1. proposed package structure
2. entity relationships
3. assumptions
4. tests you intend to implement

Wait for my approval before modifying files.
```

This approach keeps the first implementation focused and testable.

------------------------------------------------------------------------

## 12. Recommended Development Sequence

ROGUE should then be built incrementally.

``` text
M0  Repository + Architecture
        |
        v
M1  Scenario Domain Model
        |
        v
M2  Scenario Storage / API
        |
        v
M3  Map + Trajectory Editor
        |
        v
M4  Signal / SigMF Library
        |
        v
M5  RF Spectrum Planner
        |
        v
M6  Replay-Plan Compiler
        |
        v
M7  Simulated SDR Adapter
        |
        v
M8  Distributed SDR Agent
        |
        v
M9  Ettus X440 Adapter
        |
        v
M10 Deepwave AIR7311 Adapter
        |
        v
M11 Synchronized Multi-SDR Replay
        |
        v
M12 Doppler / Delay / Phase Processing
        |
        v
M13 AOA / TDOA Receiver Modeling
        |
        v
M14 RF Validation / Monitoring
```

The simulated SDR adapter should deliberately be implemented before the
real hardware adapters.

This allows most orchestration functionality to be developed and tested
without requiring permanent access to the HIL hardware.

------------------------------------------------------------------------

## 13. SDR Hardware Abstraction

A common SDR interface should be defined.

Conceptually:

``` python
class SDRAdapter(Protocol):

    async def configure(self, config): ...
    async def load_signal(self, signal): ...
    async def arm(self): ...
    async def start(self, timestamp): ...
    async def stop(self): ...
    async def status(self): ...
```

Implementations can then include:

``` text
MockSDRAdapter
EttusX440Adapter
DeepwaveAIR7311Adapter
```

The orchestrator communicates with the common interface rather than
containing device-specific logic.

------------------------------------------------------------------------

## 14. Use GitHub Issues as Claude-Sized Work Packages

Avoid broad issues such as:

``` text
Implement RF engine
```

Instead create small, testable tasks such as:

``` text
#17 Define FrequencyEvent schema
#18 Add frequency transition validation
#19 Implement SigMF metadata reader
#20 Create spectrum occupancy representation
#21 Detect channel capacity conflicts
#22 Implement mock SDR agent
#23 Add SDR health endpoint
```

Claude can then be instructed:

``` text
Implement GitHub issue #21.

First read CLAUDE.md and the applicable architecture documents.

Do not work on unrelated functionality.

Run the relevant tests before completing the task.

At completion summarize:

- files changed
- architecture decisions
- tests run
- unresolved issues
```

This provides a clear connection between requirements, implementation,
commits and Pull Requests.

------------------------------------------------------------------------

## 15. Introduce a Replay Plan

A key architectural concept for ROGUE should be the **Replay Plan**.

ROGUE therefore has two different representations:

``` text
SCENARIO
"What should happen?"
        |
        | compile
        v
REPLAY PLAN
"Exactly what must each SDR channel do?"
        |
        | execute
        v
SDR AGENTS
```

### Example Scenario

The scenario may state:

``` text
Drone A

RF link:
    recording = DJI_Control_01

    0-20 s: 2437 MHz
    20-40 s: 2462 MHz
    40-90 s: 5765 MHz
```

This describes the desired RF behavior without specifying hardware.

### Example Replay Plan

The Replay Plan compiler could translate this into operations such as:

``` text
X440-01 / channel-0

0-20 s:
    IQ = DJI_Control_01
    LO = ...
    offset = ...
    gain = ...


X440-01 / channel-1

20-40 s:
    IQ = DJI_Control_01
    LO = ...
    offset = ...
    gain = ...


AIR7311-02 / channel-2

40-90 s:
    IQ = DJI_Control_01
    LO = ...
    offset = ...
    gain = ...
```

The Replay Plan is therefore the intermediate representation between the
operational scenario and physical SDR execution.

------------------------------------------------------------------------

## 16. Responsibilities of the Replay Plan Compiler

The Replay Plan compiler is the appropriate place to solve:

-   SDR assignment;
-   SDR channel capacity;
-   sample-rate compatibility;
-   RF-band placement;
-   signal overlap;
-   frequency offsets;
-   LO selection;
-   timing;
-   gain;
-   Doppler;
-   propagation delay;
-   TDOA delay;
-   AOA/DOA phase offsets;
-   hardware resource conflicts;
-   synchronization constraints.

This keeps the scenario editor independent of the physical laboratory
topology.

A scenario can therefore be reused with different SDR configurations.

For example:

``` text
Scenario
   |
   +---- Lab Configuration A
   |       2 x Ettus X440
   |       2 x Deepwave AIR7311
   |
   +---- Lab Configuration B
   |       1 x Ettus X440
   |       4 x other SDR
   |
   +---- Simulation-only configuration
```

The scenario remains unchanged. Only compilation into the Replay Plan
changes.

------------------------------------------------------------------------

## 17. Recommended Immediate Actions

The recommended initial sequence is:

``` text
1. Create Git repository
        |
        v
2. Add architecture documentation
        |
        v
3. Create CLAUDE.md
        |
        v
4. Create develop branch
        |
        v
5. Start Claude in plan mode
        |
        v
6. Ask Claude to analyze ROGUE without coding
        |
        v
7. Create feature/scenario-domain-model
        |
        v
8. Implement scenario domain model
        |
        v
9. Run tests
        |
        v
10. Pull Request and review
        |
        v
11. Merge into develop
```

Example:

``` bash
claude --permission-mode plan
```

The first goal should not be to produce a visually impressive
application.

The first goal should be to establish a **clean, testable and
hardware-independent ROGUE core** upon which the spectrum planner,
replay compiler, distributed SDR agents and HIL functionality can
subsequently be built.

------------------------------------------------------------------------

## 18. Development Principle

The guiding principle for Claude-assisted ROGUE development should be:

> **Architecture first, small features second, hardware integration
> last.**

Claude should be used as an implementation agent operating within the
ROGUE architecture, rather than being asked to invent the architecture
while simultaneously generating the complete application.

This should make the resulting codebase easier to understand, test,
review and extend as the ROGUE HIL environment grows.
