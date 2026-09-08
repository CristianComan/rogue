import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { listAgents, type SDRAgentRecord } from "../api/agents";
import { AgentCard } from "../components/console/AgentCard";
import { colors, sectionHeadingStyle } from "../styles/tokens";

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
  const navigate = useNavigate();
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

  return (
    <div style={{ padding: 16, maxWidth: 900, margin: "0 auto" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 16 }}>
        <button type="button" onClick={() => navigate("/")}>
          ← Library
        </button>
        <h1 style={{ fontSize: 18, margin: 0 }}>SDR Console</h1>
        <button
          type="button"
          onClick={refresh}
          disabled={refreshing}
          style={{ marginLeft: "auto" }}
        >
          {refreshing ? "Testing connections…" : "Test connections (refresh)"}
        </button>
      </div>
      <div style={{ ...sectionHeadingStyle, marginBottom: 8 }}>Agents</div>
      {error && <div style={{ color: colors.severity.blocking, marginBottom: 12 }}>{error}</div>}
      {!error && agents.length === 0 && (
        <div style={{ color: colors.textMuted, fontSize: 13 }}>
          No agents have reported presence to the control plane.
        </div>
      )}
      {agents.map((agent) => (
        <AgentCard key={agent.agent_id} agent={agent} />
      ))}
    </div>
  );
}
