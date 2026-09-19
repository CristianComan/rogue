/**
 * One function per backend endpoint (backend/rogue/api/agents.py). Read-only
 * — presence upserts happen over NATS, not through this router.
 */

import { request } from "./client";
import type { PhysicalTxChannelCapability } from "../domain/replay";

export type AgentStatus = "online" | "stale";

export interface SDRAgentRecord {
  agent_id: string;
  mode: string;
  capabilities: PhysicalTxChannelCapability[];
  last_seen_at: string;
  status: AgentStatus;
}

export function listAgents(): Promise<SDRAgentRecord[]> {
  return request<SDRAgentRecord[]>("/agents");
}

export function getAgent(agentId: string): Promise<SDRAgentRecord> {
  return request<SDRAgentRecord>(`/agents/${agentId}`);
}
