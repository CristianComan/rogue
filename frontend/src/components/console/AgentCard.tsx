import { useState } from "react";
import type { SDRAgentRecord } from "../../api/agents";
import { colors, monoFontStack, sectionHeadingStyle } from "../../styles/tokens";

function statusColor(status: SDRAgentRecord["status"]): string {
  return status === "online" ? colors.status.online : colors.status.stale;
}

function ghz(range: [number, number]): string {
  return `${(range[0] / 1e9).toFixed(2)}–${(range[1] / 1e9).toFixed(2)} GHz`;
}

export function AgentCard({ agent }: { agent: SDRAgentRecord }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div
      data-testid={`agent-card-${agent.agent_id}`}
      style={{ border: `1px solid ${colors.border}`, borderRadius: 4, marginBottom: 8 }}
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
          fontFamily: monoFontStack,
        }}
      >
        <span
          aria-hidden
          style={{
            width: 8,
            height: 8,
            borderRadius: "50%",
            background: statusColor(agent.status),
            flex: "0 0 auto",
          }}
        />
        <strong style={{ fontSize: 13 }}>{agent.agent_id}</strong>
        <span style={{ fontSize: 12, color: colors.textMuted }}>{agent.mode}</span>
        <span
          style={{
            fontSize: 11,
            textTransform: "uppercase",
            letterSpacing: "0.04em",
            color: statusColor(agent.status),
            marginLeft: "auto",
          }}
        >
          {agent.status}
        </span>
        <span style={{ fontSize: 11, color: colors.textMuted }}>
          {agent.capabilities.length} ch
        </span>
      </button>
      <div style={{ padding: "0 12px 4px", fontSize: 11, color: colors.textMuted }}>
        last seen {new Date(agent.last_seen_at).toLocaleString()}
      </div>
      {expanded && (
        <table
          style={{
            width: "100%",
            borderCollapse: "collapse",
            fontSize: 12,
            fontFamily: monoFontStack,
          }}
        >
          <thead>
            <tr style={{ borderTop: `1px solid ${colors.borderLight}` }}>
              {["Channel", "Device", "Family", "Tunable range", "Max BW", "Max sample rate"].map(
                (h) => (
                  <th
                    key={h}
                    style={{
                      ...sectionHeadingStyle,
                      textAlign: "left",
                      padding: "4px 8px",
                      fontWeight: 600,
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
