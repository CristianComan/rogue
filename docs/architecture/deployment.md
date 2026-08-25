# ROGUE Deployment Architecture

## 1. Purpose

This document decomposes the deployment paragraph in
`docs/architecture/system-design.md` (section 9) into the detail needed
to actually stand up ROGUE. It defines two independent deployment
domains — the containerized control plane and the bare-metal SDR Agent
nodes — and records why they are deployed differently. The bare-metal
decision for Agent nodes is recorded formally in
`docs/decisions/ADR-004-bare-metal-sdr-agent-deployment.md`; this
document explains the mechanics.

## 2. Two deployment domains

| Domain | Runs on | Deployment method | Reaches |
|---|---|---|---|
| Control plane | One control server (or a developer laptop for local dev) | Docker Compose | Operator browsers, SDR Agent nodes (via NATS/S3), the simulated agent |
| SDR Agent node | One host per physical SDR (X440, AIR7311, ...), adjacent to the hardware | Bare-metal Python process (see ADR-004) | The control plane's NATS and MinIO endpoints over the lab network |

The simulated agent is the one exception that lives in the control-plane
domain rather than its own: it has no hardware to be adjacent to, so it
runs as a normal container in `docker-compose.yml` alongside the API.
Real Agent processes never run this way — see section 4.

## 3. Control-plane container topology

`docker-compose.yml` defines six services. Three are infrastructure,
pulled as prebuilt images from a public registry; two are ROGUE's own
code, built locally from the Dockerfiles in this repository; one is a
one-shot setup step.

| Service | Source | Role |
|---|---|---|
| `postgres` | `postgis/postgis` image | Scenario/version/run metadata, PostGIS geometry |
| `nats` | `nats` image, JetStream enabled | Agent commands, ACKs, telemetry, presence (see `sdr-architecture.md` §4) |
| `minio` | `minio/minio` image | S3-compatible SigMF recording and run-evidence storage |
| `minio-init` | `minio/mc` image | One-shot: creates the MinIO bucket, then exits |
| `api` | built from `backend/Dockerfile` | Control-plane FastAPI service |
| `simulated-agent` | built from `agents/Dockerfile` | Simulated SDR Agent (no hardware) |

### Images vs. builds

`postgres`, `nats`, and `minio`/`minio-init` are pulled, not built —
Compose fetches them from the registry the first time and caches them
locally. `api` and `simulated-agent` instead declare `build: {context:
., dockerfile: ...}`, so Compose builds a fresh image from the current
source tree every time the Dockerfile or its `COPY`-ed contents change.
Infrastructure comes from upstream; ROGUE's own code is always built
from what's actually in the repository.

### Networking

Compose places all six services on one private network and lets them
address each other by service name. This is why `api`'s environment
sets `ROGUE_DATABASE_URL` to a host of `postgres`, not `localhost` —
inside the Compose network, `postgres` resolves to that specific
container's address. From outside the Compose network (a browser on
the developer's machine, or `curl`), the same service is reached via
the `ports:` mapping instead, e.g. `localhost:8000` for `api`.

### Startup ordering

`healthcheck` blocks on `postgres` and `nats`, combined with `api`'s
`depends_on: { postgres: { condition: service_healthy }, nats: {
condition: service_healthy }, minio-init: { condition:
service_completed_successfully } }`, make Compose wait for each
dependency to actually be ready — not merely started — before bringing
up `api`. Without this, `api` could attempt its first database
connection before Postgres has finished initializing.

### Persistence

The `postgres-data`, `minio-data`, and `nats-data` volumes are what
make `docker compose down` non-destructive. Without them, stopping the
containers would discard the database and object store; with them, the
data persists on disk and reattaches on the next `docker compose up`.

## 4. SDR Agent node deployment (bare metal)

Real SDR Agent nodes — one per physical Ettus X440 or Deepwave AIR7311
unit — run as a bare-metal Python process on the host physically
connected to that hardware, **not** inside a container. See ADR-004 for
the decision record; the reasons, in brief:

- **Direct hardware access.** X440/AIR7311 are reached over
  USB/PCIe/network interfaces that a container can only see via device
  passthrough — an extra layer of fragility (device node mapping,
  udev rules, driver version skew between host and container) with no
  corresponding benefit here, since each Agent host is dedicated to one
  device family anyway.
- **Timing hardware access.** The L3/L4 synchronization classes in
  `sdr-architecture.md` §5 depend on shared PPS/10 MHz references or
  hardware PTP — physical clock lines that are simplest to reach
  directly from the host OS, not through a container network/device
  namespace.
- **Fail-safe stop guarantees.** `sdr-architecture.md` §7 requires the
  Agent to enforce watchdog/emergency-stop behaviour independent of
  control-plane availability, including process-level termination as a
  stop mechanism. A bare-metal process gives the simplest, most
  predictable mapping from "stop this process" to "this SDR stops
  transmitting."

### Mechanics

The Agent host runs the same `agents/` package as the simulated agent,
installed with `pip install .` (or `pip install -e .` for a dev
checkout) directly onto that host's Python 3.12 environment — not
`docker build`. It is started as a long-running process under whatever
process supervisor the lab standardizes on (a `systemd` unit is the
default assumption below; nothing in the code requires it):

```ini
# /etc/systemd/system/rogue-agent.service (example — not yet committed to the repo)
[Unit]
Description=ROGUE SDR Agent
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
EnvironmentFile=/etc/rogue/agent.env
ExecStart=/opt/rogue/.venv/bin/python -m agents.common.main
Restart=on-failure
RestartSec=2

[Install]
WantedBy=multi-user.target
```

`/etc/rogue/agent.env` holds the same `ROGUE_*` variables the
containerized simulated agent gets from `docker-compose.yml`, but
pointed at the control server's real address rather than a
Compose-internal service name — e.g. `ROGUE_NATS_URL=nats://control-server.lab:4222`
instead of `nats://nats:4222` — plus the per-agent device credential
referenced in section 6. `ROGUE_AGENT_MODE` distinguishes `simulated`
from a real vendor mode once `EttusX440Adapter`/`DeepwaveAIR7311Adapter`
exist (M9/M10); until then, bare-metal hosts can run the same
presence-only agent the simulated container runs, which is useful for
validating lab network reachability before adapter code exists.

### Network prerequisites

The Agent host must reach the control server's NATS port (`4222`) and
MinIO S3 endpoint (for prefetching SigMF assets, per
`sdr-architecture.md` §6) over the lab network. Per
`system-design.md` §8, this is an isolated test network by default —
the Agent host should not need, and should not be given, general
internet egress.

## 5. Local development vs. lab deployment

| | Local development | Lab / bench deployment |
|---|---|---|
| Control plane | `docker compose up` on a developer laptop | Same Compose stack, run on a dedicated control server |
| Agent(s) | `simulated-agent` container, same machine | One bare-metal process per physical SDR host, per section 4 |
| Networking | Everything on one Compose network | Control server and Agent hosts on the same isolated lab network; Agent hosts reach the control server by its real lab address |

Nothing about the domain model, RF compiler, or scenario code differs
between these two — only how the Agent process is packaged and where
it runs.

## 6. Security notes specific to deployment

Per `system-design.md` §8, each Agent has a unique machine credential.
For bare-metal Agent hosts this credential is a file on that host
(referenced by `EnvironmentFile`/config, not baked into a container
image), and it is exactly the kind of thing `CLAUDE.md` §8 already
prohibits committing to Git ("device credentials"). Provisioning of
that credential onto each Agent host is a lab operations concern, not
yet defined here.

## 7. Open items

- **Bare-metal host provisioning** (manual setup, a configuration
  management tool, or a install script) is not yet decided.
- **Vendor driver installation** on Agent hosts (UHD for Ettus, the
  Deepwave SDK) is bare-metal-host software, outside what ROGUE's own
  packaging manages — tracked against M9/M10, not resolved here.
