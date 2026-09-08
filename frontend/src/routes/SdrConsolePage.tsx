import { useCallback, useEffect, useState } from "react";
import { listAgents, type SDRAgentRecord } from "../api/agents";
import { AgentCard } from "../components/console/AgentCard";
import { AppShell } from "../components/shell/AppShell";
import { Card } from "../components/shell/Card";

/**
 * Runtime hardware inventory, independent of any single scenario draft —
 * SDRAgent/SDRDevice/PhysicalTxChannel are runtime/execution concerns
 * (domain-model.md section 8), not scenario content. "Test connection"
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

  const onlineCount = agents.filter((a) => a.status === "online").length;

  return (
    <AppShell
      breadcrumb={[{ label: "Scenario Library", to: "/" }, { label: "SDR Console" }]}
      actions={
        <button type="button" data-variant="primary" onClick={refresh} disabled={refreshing}>
          {refreshing ? "Testing connections…" : "Test connections (refresh)"}
        </button>
      }
    >
      <div
        style={{
          padding: 20,
          maxWidth: 1000,
          margin: "0 auto",
          display: "flex",
          flexDirection: "column",
          gap: 16,
        }}
      >
        <div style={{ display: "flex", gap: 12 }}>
          <StatTile label="Agents online" value={`${onlineCount} / ${agents.length}`} />
          <StatTile
            label="Total channels"
            value={String(agents.reduce((sum, a) => sum + a.capabilities.length, 0))}
          />
        </div>

        {error && (
          <div
            style={{
              padding: "8px 12px",
              background: "var(--status-danger-bg)",
              color: "var(--status-danger)",
              borderRadius: "var(--radius)",
              fontSize: 13,
            }}
          >
            {error}
          </div>
        )}

        <Card title="Agents" noPadding>
          {!error && agents.length === 0 && (
            <div
              style={{
                padding: 20,
                color: "var(--text-tertiary)",
                fontSize: 13,
                textAlign: "center",
              }}
            >
              No agents have reported presence to the control plane.
            </div>
          )}
          <div style={{ padding: agents.length > 0 ? 12 : 0 }}>
            {agents.map((agent) => (
              <AgentCard key={agent.agent_id} agent={agent} />
            ))}
          </div>
        </Card>
      </div>
    </AppShell>
  );
}

function StatTile({ label, value }: { label: string; value: string }) {
  return (
    <div
      style={{
        background: "var(--surface-card)",
        border: "1px solid var(--border-default)",
        borderRadius: "var(--radius)",
        padding: "10px 16px",
        minWidth: 140,
      }}
    >
      <div
        style={{
          fontSize: 11,
          fontWeight: 600,
          letterSpacing: "0.06em",
          textTransform: "uppercase",
          color: "var(--text-secondary)",
        }}
      >
        {label}
      </div>
      <div style={{ fontSize: 20, fontWeight: 600, marginTop: 2 }}>{value}</div>
    </div>
  );
}
