import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { getVersion } from "../api/scenarios";
import { MapCanvas } from "../components/map/MapCanvas";
import { ScenarioTimeProvider, useScenarioTime } from "../state/scenarioTimeContext";
import { scenarioDurationSeconds } from "../domain/missionEvaluator";
import type { ScenarioVersion } from "../domain/types";

/** Read-only render of one immutable published ScenarioVersion. */
export function ScenarioVersionViewerPage() {
  const { scenarioId, versionNumber } = useParams<{ scenarioId: string; versionNumber: string }>();
  const navigate = useNavigate();
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
      <div style={{ display: "flex", flexDirection: "column", height: "100vh" }}>
        <div
          style={{
            padding: 12,
            borderBottom: "1px solid #ccc",
            display: "flex",
            gap: 12,
            alignItems: "center",
          }}
        >
          <button type="button" onClick={() => navigate(`/scenarios/${scenarioId}`)}>
            ← Editor
          </button>
          <strong>Published version {versionNumber}</strong>
          {error && <span style={{ color: "crimson" }}>{error}</span>}
          {version && (
            <span>
              {version.missions.length} mission(s), {version.receivers.length} receiver(s)
            </span>
          )}
        </div>
        <div style={{ flex: 1, minHeight: 0 }}>
          <MapCanvasWithTime version={version} />
        </div>
      </div>
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
      <div style={{ padding: 12, borderTop: "1px solid #ccc" }}>
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
        <div>
          t = {scenarioTimeSeconds.toFixed(1)}s / {maxSeconds.toFixed(1)}s
        </div>
      </div>
    </div>
  );
}
