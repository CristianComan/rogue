import { useState } from "react";
import { armRun, emergencyStopRun, startRun, stopRun } from "../../api/runs";
import { useRunTime } from "../../state/runTimeContext";
import { colors } from "../../styles/tokens";
import type { RunStatus } from "../../domain/run";

const buttonStyle = (danger = false) => ({
  padding: "6px 14px",
  border: `1px solid ${danger ? colors.severity.critical : colors.border}`,
  background: danger ? colors.severity.critical : "white",
  color: danger ? "white" : "black",
  fontWeight: danger ? 700 : 400,
  cursor: "pointer",
});

/**
 * Run controls — square buttons, red-accented for the stop actions, never
 * an authoring scrub. This is a different control surface from the
 * Development page's PlaybackControls/ScrubBar on purpose (design note:
 * "Replay ≠ Dev"). Enabled/disabled per RunStatus so an operator can't send
 * an action the state machine (backend/rogue/domain/run.py) will reject.
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
    <div style={{ display: "flex", gap: 8, alignItems: "center", padding: 12 }}>
      <button
        type="button"
        disabled={!canArm || busy}
        style={buttonStyle()}
        onClick={() => act(() => armRun(scenarioId, planId, runId))}
      >
        Arm
      </button>
      <button
        type="button"
        disabled={!canStart || busy}
        style={buttonStyle()}
        onClick={() => act(() => startRun(scenarioId, planId, runId))}
      >
        Start
      </button>
      <button
        type="button"
        disabled={!canStop || busy}
        style={buttonStyle()}
        onClick={() => act(() => stopRun(scenarioId, planId, runId))}
      >
        Stop
      </button>
      <button
        type="button"
        disabled={!canEmergencyStop.includes(run.status) || busy}
        style={buttonStyle(true)}
        onClick={() => act(() => emergencyStopRun(scenarioId, planId, runId))}
      >
        Emergency stop
      </button>
      {error && <span style={{ color: colors.severity.critical, fontSize: 12 }}>{error}</span>}
    </div>
  );
}
