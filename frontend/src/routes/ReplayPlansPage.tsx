import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { listReplayPlans } from "../api/replay";
import { createRun, listRuns } from "../api/runs";
import { AppShell } from "../components/shell/AppShell";
import { Badge, type BadgeTone } from "../components/shell/Badge";
import { Card } from "../components/shell/Card";
import type { ReplayPlan } from "../domain/replay";
import type { RunStatus, ScenarioRun } from "../domain/run";

const RUN_STATUS_TONE: Record<RunStatus, BadgeTone> = {
  created: "neutral",
  preparing: "info",
  prepared: "info",
  armed: "warning",
  running: "success",
  stopping: "warning",
  stopped: "neutral",
  failed: "danger",
  emergency_stopped: "danger",
};

/**
 * Lightweight chooser between the Development page and the live Replay
 * page: compiled ReplayPlans for this scenario, each expandable to its
 * Runs, with a "Create Run" action. There is no "all runs for a scenario"
 * endpoint, so runs are only listable once a plan is selected — mirroring
 * backend/rogue/api/runs.py's actual route shape
 * (/scenarios/{id}/replay-plans/{plan_id}/runs).
 */
export function ReplayPlansPage() {
  const { scenarioId } = useParams<{ scenarioId: string }>();
  const navigate = useNavigate();
  const [plans, setPlans] = useState<ReplayPlan[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [runsByPlan, setRunsByPlan] = useState<Record<string, ScenarioRun[]>>({});
  const [creating, setCreating] = useState<string | null>(null);

  useEffect(() => {
    if (!scenarioId) return;
    listReplayPlans(scenarioId)
      .then(setPlans)
      .catch((e) => setError(String(e)));
  }, [scenarioId]);

  function loadRuns(planId: string) {
    if (!scenarioId) return;
    listRuns(scenarioId, planId)
      .then((runs) => setRunsByPlan((prev) => ({ ...prev, [planId]: runs })))
      .catch((e) => setError(String(e)));
  }

  async function handleCreateRun(planId: string) {
    if (!scenarioId) return;
    setCreating(planId);
    try {
      const run = await createRun(scenarioId, planId, "dev");
      navigate(`/scenarios/${scenarioId}/replay-plans/${planId}/runs/${run.id}`);
    } catch (e) {
      setError(String(e));
    } finally {
      setCreating(null);
    }
  }

  if (!scenarioId) return null;

  return (
    <AppShell
      breadcrumb={[
        { label: "Scenario Library", to: "/" },
        { label: "Scenario", to: `/scenarios/${scenarioId}` },
        { label: "Replay plans" },
      ]}
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
        {plans.length === 0 && !error && (
          <Card>
            <div style={{ color: "var(--text-tertiary)", fontSize: 13, textAlign: "center" }}>
              No compiled Replay Plans for this scenario yet. Compile a published version first.
            </div>
          </Card>
        )}
        {plans.map((plan) => (
          <Card
            key={plan.id}
            noPadding
            header={
              <>
                <strong style={{ fontSize: 13, fontFamily: "var(--font-mono)", fontWeight: 600 }}>
                  {plan.id.slice(0, 8)}
                </strong>
                <span style={{ fontSize: 12, color: "var(--text-secondary)" }}>
                  v{plan.scenario_version_number} · compiled{" "}
                  {new Date(plan.compiled_at).toLocaleString()}
                </span>
                <div style={{ marginLeft: "auto", display: "flex", gap: 6 }}>
                  <button type="button" onClick={() => loadRuns(plan.id)}>
                    Show runs
                  </button>
                  <button
                    type="button"
                    data-variant="primary"
                    disabled={creating === plan.id}
                    onClick={() => handleCreateRun(plan.id)}
                  >
                    {creating === plan.id ? "Creating…" : "Create run"}
                  </button>
                </div>
              </>
            }
          >
            {runsByPlan[plan.id] && (
              <div style={{ padding: 12 }}>
                <div
                  style={{
                    fontSize: 11,
                    fontWeight: 600,
                    letterSpacing: "0.06em",
                    textTransform: "uppercase",
                    color: "var(--text-secondary)",
                    marginBottom: 6,
                  }}
                >
                  Runs
                </div>
                {runsByPlan[plan.id].length === 0 && (
                  <div style={{ fontSize: 12, color: "var(--text-tertiary)" }}>No runs yet.</div>
                )}
                {runsByPlan[plan.id].map((run) => (
                  <button
                    key={run.id}
                    type="button"
                    onClick={() =>
                      navigate(`/scenarios/${scenarioId}/replay-plans/${plan.id}/runs/${run.id}`)
                    }
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: 10,
                      width: "100%",
                      textAlign: "left",
                      fontFamily: "var(--font-mono)",
                      fontSize: 12,
                      padding: "6px 10px",
                      border: "1px solid var(--border-subtle)",
                      marginBottom: 4,
                    }}
                  >
                    <span>{run.id.slice(0, 8)}</span>
                    <Badge tone={RUN_STATUS_TONE[run.status]}>{run.status}</Badge>
                    <span style={{ color: "var(--text-secondary)", marginLeft: "auto" }}>
                      {run.operator}
                    </span>
                  </button>
                ))}
              </div>
            )}
          </Card>
        ))}
      </div>
    </AppShell>
  );
}
