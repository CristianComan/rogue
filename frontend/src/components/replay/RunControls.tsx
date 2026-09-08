import { useState } from "react";
import { armRun, emergencyStopRun, startRun, stopRun } from "../../api/runs";
import { useRunTime } from "../../state/runTimeContext";
import type { RunStatus } from "../../domain/run";

/**
 * Run controls — square, flat buttons with a filled red EMERGENCY STOP,
 * matching the design canvas's run-control strip. Deliberately a
 * different control surface from the Development page's PlaybackControls/
 * ScrubBar (design note: "Replay ≠ Dev"). Each button's enabled state
 * follows the real RunStatus state machine (backend/rogue/domain/run.py),
 * not just visual mimicry — an operator can't send a transition the
 * backend will reject.
 */
export function RunControls({
  scenarioId,
  planId,
  runId,
}: {
  scenarioId: string;
  planId: string;
  runId: string;
}) {
  const { run } = useRunTime();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function act(fn: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try {
      await fn();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  const canArm = run.status === "prepared";
  const canStart = run.status === "armed";
  const canStop = run.status === "running";
  const canEmergencyStop: RunStatus[] = ["armed", "running", "stopping"];

  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 8,
        padding: "10px 14px",
        borderLeft: "1px solid var(--line)",
        background: "var(--surface-2)",
      }}
    >
      <button
        type="button"
        disabled={!canArm || busy}
        style={{ height: 32, padding: "0 14px", fontSize: 12.5, fontWeight: 600 }}
        onClick={() => act(() => armRun(scenarioId, planId, runId))}
      >
        Arm
      </button>
      <button
        type="button"
        disabled={!canStart || busy}
        style={{ height: 32, padding: "0 14px", fontSize: 12.5, fontWeight: 600 }}
        onClick={() => act(() => startRun(scenarioId, planId, runId))}
      >
        Start
      </button>
      <button
        type="button"
        disabled={!canStop || busy}
        style={{ height: 32, padding: "0 14px", fontSize: 12.5, fontWeight: 600 }}
        onClick={() => act(() => stopRun(scenarioId, planId, runId))}
      >
        Stop run
      </button>
      <button
        type="button"
        data-variant="danger"
        disabled={!canEmergencyStop.includes(run.status) || busy}
        style={{ height: 32, padding: "0 16px", fontSize: 12.5 }}
        onClick={() => act(() => emergencyStopRun(scenarioId, planId, runId))}
      >
        EMERGENCY STOP
      </button>
      {error && <span style={{ color: "var(--bad-fg)", fontSize: 12 }}>{error}</span>}
    </div>
  );
}
