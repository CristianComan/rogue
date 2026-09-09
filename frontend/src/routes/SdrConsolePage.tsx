import { useCallback, useEffect, useState } from "react";
import { listAgents, type SDRAgentRecord } from "../api/agents";
import { AgentCard } from "../components/console/AgentCard";
import { AppShell } from "../components/shell/AppShell";
import { Badge } from "../components/shell/Badge";
import { CommandButton } from "../components/shell/CommandButton";

interface FlatChannel {
  key: string;
  ch: number;
  agentId: string;
  deviceId: string;
  family: string;
  freq: string;
  sampleRate: string;
  agentTone: "ok" | "warn";
  agentStatus: string;
}

function ghz(range: [number, number]): string {
  return `${(range[0] / 1e9).toFixed(2)}–${(range[1] / 1e9).toFixed(2)} GHz`;
}

/**
 * Runtime hardware inventory, independent of any single scenario draft —
 * SDRAgent/SDRDevice/PhysicalTxChannel are runtime/execution concerns
 * (domain-model.md section 8), not scenario content. "Discover agents"
 * here is a manual refetch of GET /agents: the returned `status` is
 * computed from real heartbeat staleness (backend/rogue/domain/agent.py),
 * so it genuinely reflects whether the Agent process is alive — there is
 * no REST endpoint yet to send an ad-hoc STATUS/DISCOVER command to one
 * agent on demand (tracked as a follow-up, not faked here).
 */
export function SdrConsolePage() {
  const [agents, setAgents] = useState<SDRAgentRecord[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const refresh = useCallback(() => {
    setRefreshing(true);
    setError(null);
    listAgents()
      .then(setAgents)
      .catch((e) => setError(String(e)))
      .finally(() => setRefreshing(false));
  }, []);

  useEffect(refresh, [refresh]);

  const totalChannels = agents.reduce((sum, a) => sum + a.capabilities.length, 0);

  const channels: FlatChannel[] = agents.flatMap((a) =>
    a.capabilities.map((c) => ({
      key: `${a.agent_id}:${c.device_id}:${c.channel_index}`,
      ch: c.channel_index,
      agentId: a.agent_id,
      deviceId: c.device_id,
      family: c.device_family,
      freq: c.tunable_ranges_hz.map(ghz).join(", "),
      sampleRate: `${(c.max_sample_rate_hz / 1e6).toFixed(0)} MS/s`,
      agentTone: a.status === "online" ? "ok" : "warn",
      agentStatus: a.status,
    })),
  );

  return (
    <AppShell
      breadcrumb={[{ label: "Scenario Library", to: "/" }, { label: "SDR Console" }]}
      subnav={{
        pageTitle: "SDR Console",
        items: [
          { label: "Agents", count: agents.length, active: true },
          { label: "Devices", count: new Set(channels.map((c) => `${c.agentId}:${c.deviceId}`)).size },
          { label: "Physical TX channels", count: totalChannels },
        ],
      }}
      actions={<CommandButton label="Discover agents" onClick={refresh} disabled={refreshing} />}
    >
      <div style={{ padding: "16px 18px 24px", display: "flex", flexDirection: "column", gap: 14 }}>
        <div style={{ display: "flex", alignItems: "flex-end", justifyContent: "space-between", gap: 16 }}>
          <div>
            <div style={{ fontSize: 20, fontWeight: 600, letterSpacing: "-0.01em" }}>SDR Console</div>
            <div style={{ fontSize: 12.5, color: "var(--ink-2)", marginTop: 3 }}>
              Runtime hardware inventory — agents, devices, physical TX channels. Independent of any
              scenario.
            </div>
          </div>
          <Badge tone="bad">TX DISABLED — deny by default</Badge>
        </div>

        {error && (
          <div
            style={{
              padding: "8px 12px",
              background: "var(--bad-bg)",
              color: "var(--bad-fg)",
              border: "1px solid var(--bad-bd)",
              borderRadius: 3,
              fontSize: 13,
            }}
          >
            {error}
          </div>
        )}

        {!error && agents.length === 0 && (
          <div
            style={{
              padding: 20,
              textAlign: "center",
              color: "var(--ink-3)",
              fontSize: 13,
              background: "var(--surface)",
              border: "1px solid var(--line)",
              borderRadius: 3,
            }}
          >
            No agents have reported presence to the control plane.
          </div>
        )}

        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill,minmax(302px,1fr))", gap: 11 }}>
          {agents.map((agent) => (
            <AgentCard key={agent.agent_id} agent={agent} />
          ))}
        </div>

        {channels.length > 0 && (
          <div style={{ background: "var(--surface)", border: "1px solid var(--line)", borderRadius: 3, overflow: "hidden" }}>
            <div
              style={{
                padding: "8px 12px",
                borderBottom: "1px solid var(--line)",
                background: "var(--surface-2)",
                font: "600 11px/1.2 var(--mono)",
                letterSpacing: "0.09em",
                textTransform: "uppercase",
                color: "var(--ink-3)",
              }}
            >
              All physical TX channels
            </div>
            <div
              style={{
                display: "grid",
                gridTemplateColumns: ".7fr 1.1fr .9fr 1.3fr 1fr .9fr",
                padding: "5px 12px",
                background: "var(--surface-2)",
                borderBottom: "1px solid var(--line)",
                font: "500 10px/1 var(--mono)",
                letterSpacing: "0.06em",
                textTransform: "uppercase",
                color: "var(--ink-3)",
              }}
            >
              <div>Channel</div>
              <div>Agent</div>
              <div>Device</div>
              <div>Freq range</div>
              <div>Sample rate</div>
              <div>Agent health</div>
            </div>
            {channels.map((c) => (
              <div
                key={c.key}
                style={{
                  display: "grid",
                  gridTemplateColumns: ".7fr 1.1fr .9fr 1.3fr 1fr .9fr",
                  padding: "var(--rp) 12px",
                  borderBottom: "1px solid var(--line)",
                  alignItems: "center",
                  font: "400 11.5px/1.4 var(--mono)",
                  color: "var(--ink-2)",
                }}
              >
                <div style={{ color: "var(--ink)", fontWeight: 500 }}>ch{c.ch}</div>
                <div>{c.agentId}</div>
                <div>
                  {c.deviceId} <span style={{ color: "var(--ink-3)" }}>· {c.family}</span>
                </div>
                <div>{c.freq}</div>
                <div>{c.sampleRate}</div>
                <div>
                  <Badge tone={c.agentTone}>{c.agentStatus}</Badge>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </AppShell>
  );
}
