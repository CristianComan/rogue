import { useState } from "react";
import type { SDRAgentRecord } from "../../api/agents";
import { Badge } from "../shell/Badge";

function ghz(range: [number, number]): string {
  return `${(range[0] / 1e9).toFixed(2)}–${(range[1] / 1e9).toFixed(2)} GHz`;
}

export function AgentCard({ agent }: { agent: SDRAgentRecord }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div
      data-testid={`agent-card-${agent.agent_id}`}
      style={{
        border: "1px solid var(--border-default)",
        borderRadius: "var(--radius)",
        marginBottom: 8,
        background: "var(--surface-card)",
      }}
    >
      <button
        type="button"
        onClick={() => setExpanded((e) => !e)}
        style={{
          width: "100%",
          display: "flex",
          alignItems: "center",
          gap: 12,
          padding: "10px 12px",
          background: "none",
          border: "none",
          textAlign: "left",
          cursor: "pointer",
          fontFamily: "var(--font-mono)",
        }}
      >
        <strong style={{ fontSize: 13, fontFamily: "inherit" }}>{agent.agent_id}</strong>
        <span style={{ fontSize: 12, color: "var(--text-secondary)" }}>{agent.mode}</span>
        <Badge tone={agent.status === "online" ? "success" : "warning"}>{agent.status}</Badge>
        <span style={{ fontSize: 11, color: "var(--text-secondary)", marginLeft: "auto" }}>
          {agent.capabilities.length} ch
        </span>
        <span aria-hidden style={{ fontSize: 11, color: "var(--text-tertiary)" }}>
          {expanded ? "▲" : "▼"}
        </span>
      </button>
      <div style={{ padding: "0 12px 8px", fontSize: 11, color: "var(--text-tertiary)" }}>
        last seen {new Date(agent.last_seen_at).toLocaleString()}
      </div>
      {expanded && (
        <table
          style={{
            width: "100%",
            fontSize: 12,
            fontFamily: "var(--font-mono)",
          }}
        >
          <thead>
            <tr style={{ borderTop: "1px solid var(--border-subtle)" }}>
              {["Channel", "Device", "Family", "Tunable range", "Max BW", "Max sample rate"].map(
                (h) => (
                  <th
                    key={h}
                    style={{
                      textAlign: "left",
                      padding: "4px 8px",
                      fontSize: 11,
                      fontWeight: 600,
                      letterSpacing: "0.04em",
                      textTransform: "uppercase",
                      color: "var(--text-secondary)",
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
