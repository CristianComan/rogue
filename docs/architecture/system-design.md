# ROGUE System Design

**Baseline:** derived from ROGUE System Design Document v0.3, 20 August 2026.

## 1. Mission and system boundary

ROGUE is a distributed scenario-development, RF-environment compilation and HIL replay platform. Its web application is the Scenario Development Environment and experiment-control front end. The control plane transports metadata, commands, timing and evidence; high-rate I/Q data is prefetched to SDR nodes and is not streamed through the browser or central control path.

### 1.1 Functional decomposition

1. Scenario Development Environment
2. RF Environment Compiler
3. Spectrum Planning & Deconfliction
4. Receiver Geometry & Propagation Engine
5. SigMF Repository
6. Replay Engine
7. SDR Abstraction Layer
8. RF Distribution Network
9. RF Validation & Monitoring
10. Experiment Manager

### 1.2 Design principles

- SigMF is the native recording format.
- Scenarios describe desired RF behaviour, not vendor-specific SDR configuration.
- Logical emissions are distinct from physical SDR channels.
- A physical TX channel is a wideband RF window and may contain multiple translated/summed emissions.
- Intentional overlap is legal; impossible placement, clipping/headroom and unsafe power are validation concerns.
- Intra-band `CHANNEL_SWITCH` and inter-band `BAND_SWITCH` are distinct scenario behaviours.
- Receiver position/type are scenario entities.
- Independent RF validation verifies the generated environment against the compiled plan.
- Scenario versions and run manifests are immutable and auditable.

## 2. Users

| Role | Responsibility |
|---|---|
| Scenario designer | Areas, assets, drone missions, RF links/actions, timeline, expected outcomes |
| Test director | Approval, resource allocation, prepare/arm/start/abort, decisions |
| RF operator | Recording catalogue, RF parameter validation, device health/fault handling |
| Observer/analyst | Observe, annotate, review evidence, compare runs |
| Administrator | Users, agents, capabilities, storage, policy and system health |

## 3. Principal workflows

### Scenario authoring
Create/clone scenario → edit map/missions/RF behaviour → validate → freeze immutable version.

### Run preparation
Select approved version → compile RF environment → resolve hardware/resources → create immutable run manifest → reserve devices → prefetch/verify SigMF assets → configure agents → arm barrier.

### Execution
Release future start → evaluate deterministic timeline → agents execute local replay → collect telemetry/events → monitor RF validation → stop/abort safely.

### Review
Finalize evidence → release resources → replay timeline → annotate deviations → compare/export report.

## 4. Control-plane architecture

| Component | Responsibilities | Baseline technology |
|---|---|---|
| Web UI | Scenario library/editor, map, spectrum view, run console, evidence | React + TypeScript + Vite; MapLibre GL JS |
| Control Plane API | Auth, CRUD, validation, WebSocket, registry, audit | Python 3.12, FastAPI, Pydantic v2 |
| Run Orchestrator | Durable state machine, leases, barriers, retries, abort | Python module/service; PostgreSQL + broker |
| Database | Scenario/version/run metadata, PostGIS geometry, audit | PostgreSQL + PostGIS |
| Object storage | SigMF and run artifacts | S3-compatible MinIO |
| Message broker | Agent commands, ACKs, telemetry, presence | NATS JetStream baseline |
| SDR Agent | Discovery, cache, configure, timed replay, watchdog | Python; vendor adapters |
| Observability | Logs, metrics, traces | OpenTelemetry + Prometheus/Grafana |

The MVP is a **modular monolith plus distributed SDR Agents**, not an early microservice architecture.

## 5. UI architecture

The Scenario Editor uses a three-pane desktop layout: map, selected-object properties, and timeline/resources. The map includes scenario boundaries, restricted/no-transmit zones, drone tracks/routes, SDR/receiver sites and RF associations.

A synchronized **Spectrum Resource View** shows RF band/window, physical SDR/channel, constituent emissions, instantaneous frequency/bandwidth/power, recording source, overlap, headroom and allocation state. Timeline scrubbing must reconstruct map and spectrum state deterministically.

## 6. Run lifecycle

`DRAFT → READY → PREPARING → ARMED → RUNNING → STOPPING → COMPLETED`

Failure paths lead to `FAILED` or `ABORTED` with fail-safe TX stop and evidence finalization.

Key invariants:
- READY references a frozen/validated scenario version.
- PREPARING creates the immutable run manifest and reserves resources.
- ARMED requires all mandatory agents configured and at the barrier.
- RUNNING begins only after barrier release.
- control loss must not leave agents transmitting.

## 7. APIs

Baseline endpoints include scenario search/create/version/validate, recording ingest/browse, agent inventory, run create/prepare/arm/start/abort/events and a run WebSocket. Mutating requests use idempotency keys. Commands/events carry correlation IDs, sequence numbers and timestamps.

## 8. Security and safety

- isolated test network by default;
- approved VPN (e.g. NetBird/WireGuard) for remote connectivity;
- OIDC-compatible authentication and RBAC;
- unique machine credentials for agents;
- central authorization plus local agent re-validation;
- leases, command expiry and watchdogs;
- explicit transmit policy and operator acknowledgement;
- prominent emergency stop;
- physical cabled/attenuated RF setup as ultimate safety control;
- append-only run/audit evidence;
- no secrets in source control or scenario documents.

## 9. Deployment

MVP control server: reverse proxy, UI, API/orchestrator, PostgreSQL/PostGIS, NATS, MinIO and observability via Docker Compose. SDR nodes run the Agent, vendor drivers, local cache, timing service and watchdog. Operator workstations require only a modern browser.

## 10. Non-functional targets

- map/telemetry: 2–10 Hz;
- normal LAN control acknowledgement: <500 ms target;
- I/Q prefetched before execution;
- MVP scale: 25 concurrent missions, 16 SDR devices, 10 operators (architecture may exceed this hardware count);
- typed contracts, migration-controlled schemas, simulation fixtures and unit/integration/HIL tests;
- GeoJSON, SigMF, JSON Schema/OpenAPI interoperability.
