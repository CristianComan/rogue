import { currentFrequencyHz } from "../../domain/spectrumStrip";
import { durationToSeconds } from "../../domain/duration";
import type { DroneMission } from "../../domain/types";
import { useScenarioTime } from "../../state/scenarioTimeContext";

function mhz(hz: number): string {
  return (hz / 1e6).toFixed(1);
}

/**
 * Authored-plan preview only — reads RfBand/FrequencyBehaviour as authored,
 * not a compiled/conflict-checked spectrum plan (that's the RF Environment
 * Compiler, M5/M6). Renders every mission's RF links, stacked.
 */
export function SpectrumStrip({ missions }: { missions: DroneMission[] }) {
  const { scenarioTimeSeconds } = useScenarioTime();

  const rows = missions.flatMap((mission) => mission.rf_links.map((link) => ({ mission, link })));

  if (rows.length === 0) {
    return (
      <div style={{ padding: "8px 12px", fontSize: 12, color: "#4c5c5e" }}>
        No RF links to show.
      </div>
    );
  }

  return (
    <div style={{ padding: "4px 12px 10px", display: "flex", flexDirection: "column", gap: 6 }}>
      <div
        style={{
          fontSize: 10,
          letterSpacing: "0.04em",
          textTransform: "uppercase",
          color: "#4c5c5e",
        }}
      >
        Spectrum preview — authored plan, not compiled/conflict-checked
      </div>
      {rows.map(({ mission, link }) => {
        const currentHz = currentFrequencyHz(link, scenarioTimeSeconds);
        const span = link.band.freq_max_hz - link.band.freq_min_hz;
        const playheadPct = span > 0 ? ((currentHz - link.band.freq_min_hz) / span) * 100 : 0;

        return (
          <div
            key={link.id}
            data-testid={`spectrum-row-${link.id}`}
            style={{ display: "flex", gap: 8, alignItems: "center" }}
          >
            <div style={{ fontSize: 11, width: 140, flexShrink: 0 }}>
              {mission.name} · {link.role}
            </div>
            <div
              style={{
                position: "relative",
                flex: 1,
                height: 14,
                background: "#e4ebe8",
                border: "1px solid #ccc",
              }}
            >
              {link.frequency_behaviour.mode === "scripted" &&
                link.frequency_behaviour.scripted_changes.map((change, i) => {
                  const pct =
                    span > 0 ? ((change.frequency_hz - link.band.freq_min_hz) / span) * 100 : 0;
                  return (
                    <div
                      key={i}
                      title={`${mhz(change.frequency_hz)} MHz at t=${durationToSeconds(change.at_offset)}s`}
                      style={{
                        position: "absolute",
                        left: `${pct}%`,
                        top: 0,
                        bottom: 0,
                        width: 1,
                        background: "#4c5c5e",
                      }}
                    />
                  );
                })}
              <div
                data-testid={`spectrum-playhead-${link.id}`}
                style={{
                  position: "absolute",
                  left: `${playheadPct}%`,
                  top: -2,
                  bottom: -2,
                  width: 2,
                  background: "#b85e17",
                }}
              />
            </div>
            <div
              style={{
                fontSize: 10,
                width: 150,
                flexShrink: 0,
                fontVariantNumeric: "tabular-nums",
              }}
            >
              {mhz(link.band.freq_min_hz)}–{mhz(link.band.freq_max_hz)} MHz · now {mhz(currentHz)}
            </div>
          </div>
        );
      })}
    </div>
  );
}
