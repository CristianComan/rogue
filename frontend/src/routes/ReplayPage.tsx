import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { listRecordings } from "../api/recordings";
import { getReplayPlan } from "../api/replay";
import { getVersion } from "../api/scenarios";
import { ChannelWaterfallGrid } from "../components/replay/ChannelWaterfallGrid";
import { RunControls } from "../components/replay/RunControls";
import { RunHeader } from "../components/replay/RunHeader";
import { WatchdogFeed } from "../components/replay/WatchdogFeed";
import { MapCanvas } from "../components/map/MapCanvas";
import type { ReplayPlan } from "../domain/replay";
import type { IQRecording, ScenarioVersion } from "../domain/types";
import { RunTimeProvider, useRunTime } from "../state/runTimeContext";
import { colors } from "../styles/tokens";

/**
 * The Replay page: live/replayed drone position on the map (driven by run
 * time via RunTimeProvider, not the Development page's authoring scrub),
 * a waterfall grid per physical TX channel, the run's real watchdog/safety
 * event feed, and run controls. A fully separate route/page from Scenario
 * Development on purpose — different mental mode (watching execution vs.
 * authoring intent), different data (immutable ReplayPlan + live
 * ScenarioRun vs. an editable draft).
 */
export function ReplayPage() {
  const { scenarioId, planId, runId } = useParams<{
    scenarioId: string;
    planId: string;
    runId: string;
  }>();
  const navigate = useNavigate();
  const [plan, setPlan] = useState<ReplayPlan | null>(null);
  const [version, setVersion] = useState<ScenarioVersion | null>(null);
  const [catalogue, setCatalogue] = useState<IQRecording[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!scenarioId || !planId) return;
    let cancelled = false;
    getReplayPlan(scenarioId, planId)
      .then(async (p) => {
        if (cancelled) return;
        setPlan(p);
        const [v, recordings] = await Promise.all([
          getVersion(p.scenario_id, p.scenario_version_number),
          listRecordings({ limit: 200 }),
        ]);
        if (!cancelled) {
          setVersion(v);
          setCatalogue(recordings);
        }
      })
      .catch((e) => {
        if (!cancelled) setError(String(e));
      });
    return () => {
      cancelled = true;
    };
  }, [scenarioId, planId]);

  if (!scenarioId || !planId || !runId) return null;

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      <div
        style={{ padding: 8, borderBottom: `1px solid ${colors.border}`, display: "flex", gap: 12 }}
      >
        <button type="button" onClick={() => navigate(`/scenarios/${scenarioId}/replay`)}>
          ← Runs
        </button>
        <strong>ROGUE Replay</strong>
        {error && <span style={{ color: colors.severity.critical }}>{error}</span>}
      </div>
      {plan && version && (
        <RunTimeProvider scenarioId={scenarioId} planId={planId} runId={runId}>
          <ReplayPageBody
            plan={plan}
            version={version}
            catalogue={catalogue}
            scenarioId={scenarioId}
            planId={planId}
            runId={runId}
          />
        </RunTimeProvider>
      )}
    </div>
  );
}

function ReplayPageBody({
  plan,
  version,
  catalogue,
  scenarioId,
  planId,
  runId,
}: {
  plan: ReplayPlan;
  version: ScenarioVersion;
  catalogue: IQRecording[];
  scenarioId: string;
  planId: string;
  runId: string;
}) {
  const { runElapsedSeconds } = useRunTime();

  return (
    <div style={{ flex: 1, display: "flex", flexDirection: "column", minHeight: 0 }}>
      <RunHeader />
      <RunControls scenarioId={scenarioId} planId={planId} runId={runId} />
      <div style={{ flex: "1 1 55%", display: "flex", minHeight: 0 }}>
        <div style={{ flex: "1 1 55%", minWidth: 0 }}>
          <MapCanvas
            zones={version.zones}
            missions={version.missions}
            receivers={version.receivers}
            scenarioTimeSeconds={runElapsedSeconds}
          />
        </div>
        <div
          style={{ flex: "1 1 45%", overflowY: "auto", borderLeft: `1px solid ${colors.border}` }}
        >
          <ChannelWaterfallGrid plan={plan} catalogue={catalogue} />
        </div>
      </div>
      <div style={{ flex: "0 0 auto", borderTop: `1px solid ${colors.border}` }}>
        <WatchdogFeed />
      </div>
    </div>
  );
}
