# ADR-004: SDR Agent Nodes Deploy as Bare-Metal Processes

**Status:** Accepted baseline

## Context

The control plane (API, database, broker, object storage, and the
simulated agent) runs as Docker Compose services (`system-design.md`
§9). A separate question is how *real* SDR Agent processes — the ones
adjacent to physical Ettus X440 and Deepwave AIR7311 hardware — should
be deployed. Containerizing them was considered, since it would make
Agent deployment consistent with the control plane.

## Decision

Real SDR Agent nodes run as bare-metal Python processes on the host
physically connected to their SDR hardware, not as containers. The
simulated agent is unaffected by this decision and continues to run
containerized in `docker-compose.yml`, since it has no hardware to be
adjacent to.

## Rationale

- Avoids USB/PCIe device-passthrough complexity for hardware that a
  container would otherwise need remapped into its namespace, for no
  benefit given each Agent host is already dedicated to one device.
- Simplifies access to shared timing references (PPS/10 MHz/PTP)
  required for the L3/L4 synchronization classes in
  `sdr-architecture.md` §5.
- Gives the clearest possible mapping between "stop this OS process"
  and "this SDR stops transmitting," which matters for the
  process-termination stop path required in `sdr-architecture.md` §7.

## Consequences

- Agent hosts need their own provisioning path (Python 3.12 + vendor
  drivers installed on bare metal), separate from the control plane's
  `docker compose build`. This is not yet defined — see
  `docs/architecture/deployment.md` §7.
- The Agent codebase must not assume a Compose-internal network;
  configuration (`ROGUE_NATS_URL`, etc.) points at the control server's
  real lab address instead of a Compose service name.
- Per-agent device credentials live as files on each bare-metal host
  rather than baked into an image; these must never be committed to
  Git (`CLAUDE.md` §8 already prohibits this).
- Future vendor adapters (`EttusX440Adapter`, `DeepwaveAIR7311Adapter`,
  M9/M10) are written against this deployment model from the start,
  rather than being retrofitted from a containerized assumption.
