import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { listRecordings } from "../api/recordings";
import { getReplayPlan } from "../api/replay";
import { getVersion } from "../api/scenarios";
import { ChannelWaterfallGrid } from "../components/replay/ChannelWaterfallGrid";
import { RunControls } from "../components/replay/RunControls";
import { RunHeader } from "../components/replay/RunHeader";
import { WatchdogFeed } from "../components/replay/WatchdogFeed";
import { MapCanvas } from "../components/map/MapCanvas";
import { AppShell } from "../components/shell/AppShell";
import { Card } from "../components/shell/Card";
import type { ReplayPlan } from "../domain/replay";
import type { IQRecording, ScenarioVersion } from "../domain/types";
import { RunTimeProvider, useRunTime } from "../state/runTimeContext";

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
    <AppShell
      scroll={false}
      breadcrumb={[
        { label: "Scenario Library", to: "/" },
        { label: "Runs", to: `/scenarios/${scenarioId}/replay` },
        { label: `Run ${runId.slice(0, 8)}` },
      ]}
    >
      <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
        {error && (
          <div
            style={{
              padding: "8px 20px",
              background: "var(--status-danger-bg)",
              color: "var(--status-danger)",
              fontSize: 13,
            }}
          >
            {error}
          </div>
        )}
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
    </AppShell>
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
    <div
      style={{
        flex: 1,
        display: "flex",
        flexDirection: "column",
        minHeight: 0,
        padding: "var(--space-2)",
        gap: "var(--space-2)",
      }}
    >
      <Card noPadding>
        <div style={{ display: "flex", alignItems: "center", flexWrap: "wrap" }}>
          <RunHeader />
          <div style={{ marginLeft: "auto", paddingRight: 12 }}>
            <RunControls scenarioId={scenarioId} planId={planId} runId={runId} />
          </div>
        </div>
      </Card>
      <div style={{ flex: "1 1 55%", display: "flex", gap: "var(--space-2)", minHeight: 0 }}>
        <div style={{ flex: "1 1 55%", minWidth: 0 }}>
          <Card title="Live position" noPadding style={{ height: "100%" }}>
            <MapCanvas
              zones={version.zones}
              missions={version.missions}
              receivers={version.receivers}
              scenarioTimeSeconds={runElapsedSeconds}
            />
          </Card>
        </div>
        <div style={{ flex: "1 1 45%", minWidth: 0 }}>
          <Card
            noPadding
            style={{ height: "100%" }}
            bodyStyle={{ overflowY: "auto", height: "100%" }}
          >
            <ChannelWaterfallGrid plan={plan} catalogue={catalogue} />
          </Card>
        </div>
      </div>
      <div style={{ flex: "0 0 auto" }}>
        <Card noPadding>
          <WatchdogFeed />
        </Card>
      </div>
    </div>
  );
}
