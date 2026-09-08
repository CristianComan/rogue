import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { listReplayPlans } from "../api/replay";
import { createRun, listRuns } from "../api/runs";
import type { ReplayPlan } from "../domain/replay";
import type { ScenarioRun } from "../domain/run";
import { colors, monoFontStack, sectionHeadingStyle } from "../styles/tokens";

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
    <div style={{ padding: 16, maxWidth: 900, margin: "0 auto" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 16 }}>
        <button type="button" onClick={() => navigate(`/scenarios/${scenarioId}`)}>
          ← Editor
        </button>
        <h1 style={{ fontSize: 18, margin: 0 }}>Replay plans</h1>
      </div>
      {error && <div style={{ color: colors.severity.critical, marginBottom: 12 }}>{error}</div>}
      {plans.length === 0 && !error && (
        <div style={{ color: colors.textMuted, fontSize: 13 }}>
          No compiled Replay Plans for this scenario yet. Compile a published version first.
        </div>
      )}
      {plans.map((plan) => (
        <div
          key={plan.id}
          style={{
            border: `1px solid ${colors.border}`,
            borderRadius: 4,
            marginBottom: 12,
            padding: 12,
          }}
        >
          <div
            style={{ display: "flex", alignItems: "center", gap: 12, fontFamily: monoFontStack }}
          >
            <strong style={{ fontSize: 13 }}>{plan.id}</strong>
            <span style={{ fontSize: 12, color: colors.textMuted }}>
              v{plan.scenario_version_number} · compiled{" "}
              {new Date(plan.compiled_at).toLocaleString()}
            </span>
            <button type="button" onClick={() => loadRuns(plan.id)} style={{ marginLeft: "auto" }}>
              Show runs
            </button>
            <button
              type="button"
              disabled={creating === plan.id}
              onClick={() => handleCreateRun(plan.id)}
            >
              {creating === plan.id ? "Creating…" : "Create run"}
            </button>
          </div>
          {runsByPlan[plan.id] && (
            <div style={{ marginTop: 8 }}>
              <div style={sectionHeadingStyle}>Runs</div>
              {runsByPlan[plan.id].length === 0 && (
                <div style={{ fontSize: 12, color: colors.textMuted }}>No runs yet.</div>
              )}
              {runsByPlan[plan.id].map((run) => (
                <button
                  key={run.id}
                  type="button"
                  onClick={() =>
                    navigate(`/scenarios/${scenarioId}/replay-plans/${plan.id}/runs/${run.id}`)
                  }
                  style={{
                    display: "block",
                    width: "100%",
                    textAlign: "left",
                    fontFamily: monoFontStack,
                    fontSize: 12,
                    padding: "4px 8px",
                    border: `1px solid ${colors.borderLight}`,
                    marginBottom: 4,
                    cursor: "pointer",
                  }}
                >
                  {run.id} · {run.status} · {run.operator}
                </button>
              ))}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
