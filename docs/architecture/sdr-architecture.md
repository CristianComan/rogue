# ROGUE SDR Architecture

## 1. SDR Agent pattern

Each SDR node runs a lightweight Agent adjacent to the hardware. The central control plane does not directly manipulate vendor drivers.

The Agent:
- discovers devices/channels and reports actual capabilities;
- maintains local SigMF cache;
- validates configuration against hardware and local policy;
- reserves exclusive resources using leases;
- configures and arms devices;
- executes scheduled replay using the best supported timing method;
- publishes acknowledgements, telemetry and alarms;
- enforces watchdog and fail-safe stop;
- records actual configuration readback and timing method;
- exposes vendor-neutral high-level operations.

SoapyRemote may be used for diagnostics, but is not the production orchestration abstraction.

## 2. Vendor-neutral adapter contract

Conceptual interface:

```python
class SDRAdapter(Protocol):
    async def discover(self): ...
    async def capabilities(self): ...
    async def reserve(self, lease): ...
    async def preflight(self, recording, config): ...
    async def configure(self, config): ...
    async def arm(self, start_spec): ...
    async def start(self): ...
    async def stop(self): ...
    async def emergency_stop(self): ...
    async def status(self): ...
```

Implementations initially include:
- `MockSDRAdapter` / simulated agent;
- `EttusX440Adapter`;
- `DeepwaveAIR7311Adapter`.

Vendor libraries (UHD, SoapySDR, libiio or other device APIs) stay behind adapters.

## 3. Initial laboratory hardware profile

Initial target:
- 2 × Ettus USRP X440, modeled as 8 TX channels per unit (16 total working-profile channels);
- 2 × Deepwave AIR7311, modeled as 4 TX channels per unit (8 total working-profile channels);
- 24 physical TX channels in the initial planning pool.

Static profiles are planning defaults only. Runtime discovery/readback is authoritative.

The design baseline states that native X440 RF coverage does not cover 5.2/5.8 GHz. Therefore those bands are normally assigned to AIR7311-capable paths unless an explicit external frequency-conversion chain is modeled. X440 paths may serve 2.4 GHz and other supported sub-4-GHz windows.

## 4. Agent command model

Versioned commands include:
- reserve / release;
- prefetch / verify;
- configure;
- arm;
- start-at;
- stop;
- emergency-stop;
- status.

Every command/ACK includes correlation ID, sequence, timestamps, state and structured errors. Commands are idempotent, expire, and are rejected when stale or outside an active lease.

## 5. Timing and synchronization classes

| Level | Method | Intended use |
|---|---|---|
| L0 | simulated/no SDR | UI, scenario design, CI |
| L1 | NTP hosts + software barrier | early functional tests; ms to tens-of-ms |
| L2 | scheduled local future start | improved LAN repeatability |
| L3 | shared PPS/10 MHz or hardware PTP + timed commands | tightly aligned replay where supported |
| L4 | L3 + reference/loopback measurement | evidence-grade measured alignment |

A run declares required synchronization class/tolerance. The system must not promise hard real-time behaviour over ordinary Ethernet.

## 6. Local caching and streaming

I/Q is prefetched before a run, checksum-verified and replayed from local storage. Streaming uses bounded buffers; no full-file RAM load. The control network is not the sample transport path.

## 7. Safety

Agent safety is independent of control-plane availability:
- default deny TX;
- explicit RF approval/environment gate;
- local frequency/power/profile checks;
- cabled/attenuated mode by default for automated tests;
- lease expiry and watchdog stop;
- process termination stop where technically possible;
- emergency stop;
- reject unsigned/incorrect manifests and incompatible settings;
- record stop acknowledgements and faults.

Real hardware tests must never automatically enable uncontrolled over-the-air transmission.

## 8. Simulation first

The simulated agent is a first-class implementation, not a throwaway mock. It shall model transfer delay, clock drift, underrun, command loss, device failure and reconnect. This enables CI, operator training and orchestration development before hardware integration.
