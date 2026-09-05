import { useScenarioTime } from "../../state/scenarioTimeContext";

const SPEEDS = [0.5, 1, 2, 4, 8];

export function PlaybackControls() {
  const { isPlaying, play, pause, playbackSpeed, setPlaybackSpeed } = useScenarioTime();

  return (
    <div style={{ display: "flex", gap: 8, alignItems: "center", padding: "0 12px" }}>
      <button type="button" onClick={isPlaying ? pause : play}>
        {isPlaying ? "Pause" : "Play"}
      </button>
      <label style={{ fontSize: 12, display: "flex", gap: 4, alignItems: "center" }}>
        Speed
        <select value={playbackSpeed} onChange={(e) => setPlaybackSpeed(Number(e.target.value))}>
          {SPEEDS.map((speed) => (
            <option key={speed} value={speed}>
              {speed}×
            </option>
          ))}
        </select>
      </label>
    </div>
  );
}
