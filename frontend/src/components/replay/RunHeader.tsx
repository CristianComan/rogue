import type { ReactNode } from "react";
import { useRunTime } from "../../state/runTimeContext";
import { colors, monoFontStack, sectionHeadingStyle } from "../../styles/tokens";
import type { RunStatus } from "../../domain/run";

function statusColor(status: RunStatus): string {
  switch (status) {
    case "running":
      return colors.status.online;
    case "armed":
    case "preparing":
    case "prepared":
    case "stopping":
      return colors.severity.warning;
    case "failed":
    case "emergency_stopped":
      return colors.severity.critical;
    default:
      return colors.status.offline;
  }
}

function formatElapsed(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m.toString().padStart(2, "0")}:${s.toString().padStart(2, "0")}`;
}

function Tile({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div
      style={{
        border: `1px solid ${colors.border}`,
        borderRadius: 4,
        padding: "8px 12px",
        minWidth: 140,
      }}
    >
      <div style={sectionHeadingStyle}>{label}</div>
      <div style={{ fontFamily: monoFontStack, fontSize: 16, marginTop: 4 }}>{children}</div>
    </div>
  );
}

/** Run status header — square, red-accented on stop actions, never an authoring scrub (RunControls). */
export function RunHeader() {
  const { run, runElapsedSeconds, nowMs } = useRunTime();

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
    <div style={{ display: "flex", gap: 12, padding: 12, flexWrap: "wrap" }}>
      <Tile label="Run state">
        <span style={{ color: statusColor(run.status), textTransform: "uppercase" }}>
          {run.status}
        </span>
        <div style={{ fontSize: 12, color: colors.textMuted }}>
          {formatElapsed(runElapsedSeconds)}
        </div>
      </Tile>
      <Tile label="Operator">{run.operator}</Tile>
      <Tile label="Tx channels">{activeLeases.length} leased</Tile>
      <Tile label="Shortest lease">
        {shortestLeaseSeconds === null ? "—" : formatElapsed(Math.max(0, shortestLeaseSeconds))}
      </Tile>
      <Tile label="Safety events">
        <span style={{ color: criticalEvents > 0 ? colors.severity.critical : undefined }}>
          {criticalEvents} critical
        </span>
        <div style={{ fontSize: 12, color: colors.textMuted }}>
          {warningEvents} warnings this run
        </div>
      </Tile>
    </div>
  );
}
