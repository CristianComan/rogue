import type { ReactNode } from "react";
import { useRunTime } from "../../state/runTimeContext";
import type { RunStatus } from "../../domain/run";
import type { Tone } from "../../styles/tokens";

function runTone(status: RunStatus): Tone {
  switch (status) {
    case "running":
      return "ok";
    case "armed":
    case "preparing":
    case "prepared":
    case "stopping":
      return "warn";
    case "failed":
    case "emergency_stopped":
      return "bad";
    default:
      return "mute";
  }
}

function formatElapsed(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m.toString().padStart(2, "0")}:${s.toString().padStart(2, "0")}`;
}

function StatTile({
  label,
  value,
  sub,
  tone,
}: {
  label: string;
  value: ReactNode;
  sub?: string;
  tone?: Tone;
}) {
  return (
    <div style={{ padding: "10px 14px", borderRight: "1px solid var(--line)", minWidth: 132 }}>
      <div
        style={{
          font: "500 10px/1 var(--mono)",
          letterSpacing: "0.08em",
          textTransform: "uppercase",
          color: "var(--ink-3)",
        }}
      >
        {label}
      </div>
      <div
        style={{ font: "500 15px/1.5 var(--mono)", color: tone ? `var(--${tone}-fg)` : undefined }}
      >
        {value}
      </div>
      {sub && (
        <div style={{ font: "400 10.5px/1.2 var(--mono)", color: "var(--ink-3)" }}>{sub}</div>
      )}
    </div>
  );
}

/** Run status header — matches the design canvas's run-tile + stat-tile row, with a real live-pulse dot while running. */
export function RunHeader() {
  const { run, runElapsedSeconds, nowMs } = useRunTime();
  const tone = runTone(run.status);

  const activeLeases = run.device_leases;
  const shortestLeaseSeconds =
    activeLeases.length > 0
      ? Math.min(...activeLeases.map((l) => (new Date(l.expires_at).getTime() - nowMs) / 1000))
      : null;

  const criticalEvents = run.events.filter(
    (e) => e.severity === "blocking" || e.kind === "error" || e.kind === "emergency_stopped",
  ).length;
  const warningEvents = run.events.filter((e) => e.severity === "warning").length;

  return (
    <div style={{ display: "flex", alignItems: "stretch", flexWrap: "wrap" }}>
      <div
        style={{
          padding: "10px 14px",
          borderRight: "1px solid var(--line)",
          display: "flex",
          flexDirection: "column",
          gap: 4,
          minWidth: 220,
        }}
      >
        <div
          style={{
            font: "500 10px/1 var(--mono)",
            letterSpacing: "0.08em",
            textTransform: "uppercase",
            color: "var(--ink-3)",
          }}
        >
          Run
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: 6,
              padding: "2px 9px",
              borderRadius: 2,
              font: "600 12px/1.5 var(--mono)",
              color: `var(--${tone}-fg)`,
              background: `var(--${tone}-bg)`,
              border: `1px solid var(--${tone}-bd)`,
            }}
          >
            <span
              aria-hidden
              style={{
                width: 7,
                height: 7,
                borderRadius: "50%",
                background: `var(--${tone}-fg)`,
                animation:
                  run.status === "running" ? "livepulse 1.6s ease-in-out infinite" : undefined,
              }}
            />
            {run.status.replace(/_/g, " ").toUpperCase()}
          </span>
          <span style={{ font: "500 15px/1 var(--mono)" }}>{formatElapsed(runElapsedSeconds)}</span>
        </div>
        <div style={{ font: "400 11px/1.4 var(--mono)", color: "var(--ink-3)" }}>
          run-{run.id.slice(0, 6)} · plan {run.replay_plan_id.slice(0, 6)}
        </div>
      </div>
      <StatTile label="Operator" value={run.operator} />
      <StatTile label="TX channels" value={`${activeLeases.length}`} sub="leased" />
      <StatTile
        label="Shortest lease"
        value={
          shortestLeaseSeconds === null ? "—" : formatElapsed(Math.max(0, shortestLeaseSeconds))
        }
        tone={shortestLeaseSeconds !== null && shortestLeaseSeconds < 30 ? "warn" : undefined}
      />
      <StatTile
        label="Safety events"
        value={`${criticalEvents} critical`}
        sub={`${warningEvents} warnings this run`}
        tone={criticalEvents > 0 ? "bad" : undefined}
      />
    </div>
  );
}
