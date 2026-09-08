import { useState } from "react";
import type { SDRAgentRecord } from "../../api/agents";
import { Badge } from "../shell/Badge";

function ghz(range: [number, number]): string {
  return `${(range[0] / 1e9).toFixed(2)}–${(range[1] / 1e9).toFixed(2)} GHz`;
}

function fieldRow(label: string, value: string, tone?: string) {
  return (
    <>
      <span style={{ color: "var(--ink-3)" }}>{label}</span>
      <span style={{ color: tone ?? "var(--ink)", minWidth: 0, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
        {value}
      </span>
    </>
  );
}

/**
 * Matches the design canvas's agent-card field grid (host/family/clock/
 * devices/last seen/lease). SDRAgentRecord (backend/rogue/domain/agent.py)
 * only actually carries agent_id/mode/capabilities/last_seen_at/status —
 * no host, clock-lock, or lease-holder telemetry exists yet (a real,
 * documented gap — see ADR-011's follow-ups), so those rows say so rather
 * than inventing a value. family/devices are derived from `capabilities`,
 * which is real.
 */
export function AgentCard({ agent }: { agent: SDRAgentRecord }) {
  const [expanded, setExpanded] = useState(false);

  const deviceIds = [...new Set(agent.capabilities.map((c) => c.device_id))];
  const families = [...new Set(agent.capabilities.map((c) => c.device_family))];
  const tone = agent.status === "online" ? "ok" : "warn";

  return (
    <div
      data-testid={`agent-card-${agent.agent_id}`}
      style={{
        border: "1px solid var(--line)",
        borderRadius: 3,
        background: "var(--surface)",
        display: "flex",
        flexDirection: "column",
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 8,
          padding: "9px 11px",
          borderBottom: "1px solid var(--line)",
          background: "var(--surface-2)",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 8, minWidth: 0 }}>
          <span
            aria-hidden
            style={{ width: 8, height: 8, borderRadius: "50%", background: `var(--${tone}-fg)`, flex: "0 0 8px" }}
          />
          <span style={{ fontWeight: 600, fontSize: 13 }}>{agent.agent_id}</span>
        </div>
        <Badge tone={tone}>{agent.status}</Badge>
      </div>
      <div
        style={{
          padding: "9px 11px",
          display: "grid",
          gridTemplateColumns: "auto 1fr",
          gap: "3px 10px",
          font: "400 11.5px/1.5 var(--mono)",
        }}
      >
        {fieldRow("mode", agent.mode)}
        {fieldRow("family", families.join(", ") || "—")}
        {fieldRow("devices", deviceIds.length > 0 ? `${deviceIds.length} device(s) · ${agent.capabilities.length} TX ch` : "0")}
        {fieldRow("last seen", new Date(agent.last_seen_at).toLocaleTimeString())}
        {fieldRow("host", "not reported yet", "var(--ink-3)")}
        {fieldRow("clock", "not reported yet", "var(--ink-3)")}
      </div>
      <div style={{ margin: "0 11px 9px" }}>
        <button type="button" onClick={() => setExpanded((e) => !e)} style={{ width: "100%", fontSize: 12 }}>
          {expanded ? "Hide channels ▲" : `Channels (${agent.capabilities.length}) ▾`}
        </button>
      </div>
      {expanded && (
        <table
          style={{
            width: "100%",
            fontSize: 12,
            fontFamily: "var(--mono)",
          }}
        >
          <thead>
            <tr style={{ borderTop: "1px solid var(--line)" }}>
              {["Channel", "Device", "Family", "Tunable range", "Max BW", "Max sample rate"].map(
                (h) => (
                  <th
                    key={h}
                    style={{
                      textAlign: "left",
                      padding: "4px 8px",
                      fontSize: 10,
                      fontWeight: 500,
                      letterSpacing: "0.06em",
                      textTransform: "uppercase",
                      color: "var(--ink-3)",
                    }}
                  >
                    {h}
                  </th>
                ),
              )}
            </tr>
          </thead>
          <tbody>
            {agent.capabilities.map((cap) => (
              <tr key={`${cap.device_id}:${cap.channel_index}`}>
                <td style={{ padding: "4px 8px" }}>{cap.channel_index}</td>
                <td style={{ padding: "4px 8px" }}>{cap.device_id}</td>
                <td style={{ padding: "4px 8px" }}>{cap.device_family}</td>
                <td style={{ padding: "4px 8px" }}>{cap.tunable_ranges_hz.map(ghz).join(", ")}</td>
                <td style={{ padding: "4px 8px" }}>
                  {(cap.max_usable_bandwidth_hz / 1e6).toFixed(0)} MHz
                </td>
                <td style={{ padding: "4px 8px" }}>
                  {(cap.max_sample_rate_hz / 1e6).toFixed(0)} MS/s
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
