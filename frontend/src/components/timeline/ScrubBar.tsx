import { useScenarioTime } from "../../state/scenarioTimeContext";

export function ScrubBar({ maxSeconds }: { maxSeconds: number }) {
  const { scenarioTimeSeconds, seek } = useScenarioTime();

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 4, padding: "8px 12px" }}>
      <input
        type="range"
        min={0}
        max={maxSeconds}
        step={Math.max(maxSeconds / 500, 0.01)}
        value={scenarioTimeSeconds}
        onChange={(e) => seek(Number(e.target.value))}
        style={{ width: "100%" }}
      />
      <div style={{ fontSize: 12, fontVariantNumeric: "tabular-nums" }}>
        t = {scenarioTimeSeconds.toFixed(1)}s / {maxSeconds.toFixed(1)}s
      </div>
    </div>
  );
}
