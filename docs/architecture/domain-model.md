# ROGUE Domain Model

## 1. Modeling rule

The canonical domain model represents scenario intent. It must not encode a permanent mapping from a drone or RF link to a vendor device/channel. Physical assignments exist in the compiled run manifest/Replay Plan.

## 2. Core aggregate

```text
Scenario
  └─ ScenarioVersion (immutable)
       ├─ Area / restricted zones
       ├─ DroneMission[]
       │    ├─ Platform
       │    ├─ Trajectory
       │    └─ DroneRfLink[]
       │         ├─ RfBand / band plan
       │         ├─ RfEmission[]
       │         └─ FrequencyBehaviour
       ├─ Receiver[]
       ├─ Timeline events
       └─ Recording references

ScenarioRun
  ├─ immutable RunManifest / ReplayPlan
  ├─ DeviceLease[]
  ├─ RunEvent[]
  ├─ AuditEvent[]
  └─ validation/evidence artifacts
```

## 3. Entities

### Scenario
Stable identity, owner, tags, coordinate system, area of operation, variables and current approved version.

### ScenarioDraft
Editable working representation with optimistic concurrency. Publishing creates an immutable `ScenarioVersion`.

### ScenarioVersion
Immutable, schema-versioned scenario document including missions, RF intent, receivers, timeline, validation result, author and change note.

### DroneMission
Platform, mission type, geometry, altitude/speed profiles, start policy, behaviour parameters and RF links.

Supported mission templates:
- waypoint transit;
- orbit;
- racetrack;
- grid/lawnmower search;
- perimeter patrol;
- loiter then depart;
- swarm/staggered arrival;
- scripted timestamped track.

### Trajectory
GeoJSON geometry plus timing/kinematic constraints. Canonical mission state is evaluated from scenario time, not accumulated UI timer ticks. At arbitrary time `t`, the mission engine returns position, velocity/ground speed, altitude, heading, phase and completion state.

### IQRecording
Immutable SigMF asset/version reference with metadata/data object locations, SHA-256, sample format/rate/count, duration, provenance, access classification and allowed use/frequency constraints. Unknown SigMF extension fields are retained.

### DroneRfLink
Logical RF relationship owned by a platform/mission, such as C2, telemetry or video/data. Defines band plan, allowed frequencies/ranges, switching policy and associated emissions/recordings.

### RfEmission
A logical emitted waveform with recording mapping and per-emission processing parameters. It is not a physical TX channel.

### FrequencyBehaviour / FrequencyEvent
Defines time-varying frequency behaviour and realized changes. Supports scripted, mission/position-triggered, deterministic probabilistic/adaptive, and approved external/state-triggered switching. Random seeds and realized choices are recorded for repeatability.

### Receiver
Geodetic position plus receiver type and geometry. Types are `MONITOR`, `TDOA`, and `AOA_DOA`.

### SDRAgent / SDRDevice / PhysicalTxChannel
Runtime inventory and capabilities: presence, versions, clocks, frequency/sample-rate/gain ranges, channels, health and lease state. Hardware data is discovered/read back at runtime.

### ScenarioRun
Immutable execution identity referencing the approved scenario version and compiled manifest, with allocations, state, timestamps, operator, events, annotations and evidence.

## 4. Timeline model

Events may be:
- absolute scenario time (`T+hh:mm:ss.sss`);
- mission-relative (start, waypoint, area entry, phase completion);
- manual gated operator event;
- approved external event;
- safety event (lease expiry, alarm, clock degradation, underrun, no-transmit violation, emergency stop).

MVP implements absolute and mission-relative events first.

## 5. Versioning and immutability

- UUID identifiers and UTC timestamps.
- Scenario documents contain explicit `schema_version`.
- Drafts use optimistic concurrency.
- Published scenario versions are immutable.
- Run manifests are immutable.
- Referenced records are deprecated rather than destructively deleted.
- Run evidence is append-only for ordinary users.

## 6. Validation invariants

Domain validation covers schema/references, geometry, mission timing/kinematics, recording integrity and timeline consistency. RF allocation and hardware compatibility are compiler/readiness concerns and must not leak vendor assumptions into the scenario model.

Intentional RF overlap must not be rejected by the domain schema.

## 7. Portable scenario representation

Use versioned JSON with GeoJSON geometry and stable recording references. Physical SDR/channel assignments are not canonical scenario content. Optional resource preferences/constraints may be expressed, but actual allocations are stored only in the run manifest.
