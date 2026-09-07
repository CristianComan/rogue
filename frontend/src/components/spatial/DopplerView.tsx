import { rangeAndRangeRate } from "../../domain/doppler";
import type { DroneMission, Receiver } from "../../domain/types";
import { monoFontStack, sectionHeadingStyle } from "../../styles/tokens";

/**
 * Receiver x mission range/range-rate at the current scenario time — the
 * geometry an operator needs to reason about Doppler shift on a link
 * before compilation. See domain/doppler.ts for the pure calculation
 * (reuses missionEvaluator.evaluateMissionState, sampled twice).
 */
export function DopplerView({
  receivers,
  missions,
  scenarioTimeSeconds,
}: {
  receivers: Receiver[];
  missions: DroneMission[];
  scenarioTimeSeconds: number;
}) {
  if (receivers.length === 0 || missions.length === 0) {
    return (
      <div style={{ padding: "8px 12px", fontSize: 12, color: "#4c5c5e" }}>
        Add at least one receiver and one mission to see range/range-rate geometry.
      </div>
    );
  }

  return (
    <div style={{ fontFamily: monoFontStack }}>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
        <thead>
          <tr>
            {["Receiver", "Mission", "Range", "Range-rate"].map((h) => (
              <th key={h} style={{ ...sectionHeadingStyle, textAlign: "left", padding: "4px 8px" }}>
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {receivers.flatMap((receiver) =>
            missions.map((mission) => {
              const { rangeM, rangeRateMps } = rangeAndRangeRate(
                receiver,
                mission,
                scenarioTimeSeconds,
              );
              return (
                <tr key={`${receiver.id}:${mission.id}`}>
                  <td style={{ padding: "4px 8px" }}>{receiver.name}</td>
                  <td style={{ padding: "4px 8px" }}>{mission.name}</td>
                  <td style={{ padding: "4px 8px" }}>{(rangeM / 1000).toFixed(3)} km</td>
                  <td style={{ padding: "4px 8px" }}>
                    {rangeRateMps >= 0 ? "+" : ""}
                    {rangeRateMps.toFixed(1)} m/s {rangeRateMps >= 0 ? "(receding)" : "(closing)"}
                  </td>
                </tr>
              );
            }),
          )}
        </tbody>
      </table>
    </div>
  );
}
