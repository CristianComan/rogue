import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { getVersion } from "../api/scenarios";
import { MapCanvas } from "../components/map/MapCanvas";
import { AppShell } from "../components/shell/AppShell";
import { Card } from "../components/shell/Card";
import { ScenarioTimeProvider, useScenarioTime } from "../state/scenarioTimeContext";
import { scenarioDurationSeconds } from "../domain/missionEvaluator";
import type { ScenarioVersion } from "../domain/types";

/** Read-only render of one immutable published ScenarioVersion. */
export function ScenarioVersionViewerPage() {
  const { scenarioId, versionNumber } = useParams<{ scenarioId: string; versionNumber: string }>();
  const [version, setVersion] = useState<ScenarioVersion | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!scenarioId || !versionNumber) return;
    getVersion(scenarioId, Number(versionNumber))
      .then(setVersion)
      .catch((e) => setError(String(e)));
  }, [scenarioId, versionNumber]);

  const maxSeconds = Math.max(1, scenarioDurationSeconds(version?.missions ?? []));

  return (
    <ScenarioTimeProvider maxSeconds={maxSeconds}>
      <AppShell
        scroll={false}
        breadcrumb={[
          { label: "Scenario Library", to: "/" },
          { label: "Scenario", to: `/scenarios/${scenarioId}` },
          { label: `Version ${versionNumber}` },
        ]}
        actions={
          version && (
            <span style={{ fontSize: 12, color: "var(--text-secondary)" }}>
              {version.missions.length} mission(s), {version.receivers.length} receiver(s)
            </span>
          )
        }
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
          <div style={{ flex: 1, minHeight: 0, padding: "var(--space-2)" }}>
            <Card noPadding style={{ height: "100%" }} bodyStyle={{ height: "100%" }}>
              <MapCanvasWithTime version={version} />
            </Card>
          </div>
        </div>
      </AppShell>
    </ScenarioTimeProvider>
  );
}

function MapCanvasWithTime({ version }: { version: ScenarioVersion | null }) {
  const { scenarioTimeSeconds, seek } = useScenarioTime();
  const maxSeconds = Math.max(1, scenarioDurationSeconds(version?.missions ?? []));

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      <div style={{ flex: 1, minHeight: 0 }}>
        <MapCanvas
          zones={version?.zones ?? []}
          missions={version?.missions ?? []}
          receivers={version?.receivers ?? []}
          scenarioTimeSeconds={scenarioTimeSeconds}
        />
      </div>
      <div style={{ padding: 12, borderTop: "1px solid var(--border-subtle)" }}>
        <input
          type="range"
          min={0}
          max={maxSeconds}
          step={maxSeconds / 500}
          value={scenarioTimeSeconds}
          onChange={(e) => seek(Number(e.target.value))}
          style={{ width: "100%" }}
          disabled={!version}
        />
        <div
          style={{ fontSize: 12, color: "var(--text-secondary)", fontFamily: "var(--font-mono)" }}
        >
          t = {scenarioTimeSeconds.toFixed(1)}s / {maxSeconds.toFixed(1)}s
        </div>
      </div>
    </div>
  );
}
