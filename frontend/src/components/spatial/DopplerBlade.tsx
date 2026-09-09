import { useState } from "react";
import { rangeAndRangeRate, sampleRangeSeries } from "../../domain/doppler";
import type { DroneMission, Receiver } from "../../domain/types";
import { Blade } from "../shell/Blade";

const MISSION_COLOR_HUES = [245, 30, 155, 300, 60, 200];

function colorForMission(missions: DroneMission[], missionId: string): string {
  const index = missions.findIndex((m) => m.id === missionId);
  const hue = MISSION_COLOR_HUES[Math.max(0, index) % MISSION_COLOR_HUES.length];
  return `oklch(0.6 0.15 ${hue})`;
}

function fmtT(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m.toString().padStart(2, "0")}:${s.toString().padStart(2, "0")}`;
}

/** An evenly-sampled series as an SVG polyline `points` string over a 0..100 x 0..28 viewBox. */
function sparklinePoints(values: number[]): string {
  if (values.length === 0) return "";
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  return values
    .map((v, i) => {
      const x = (i / Math.max(1, values.length - 1)) * 100;
      const y = 28 - ((v - min) / range) * 28;
      return `${x.toFixed(2)},${y.toFixed(2)}`;
    })
    .join(" ");
}

/**
 * The Doppler geometry sub-view, as a wide (1080px) blade rather than an
 * in-panel tab — matching the design canvas's "D · Sub-view of Spatial
 * knowledge" overlay, including its independent scrub (a receiver/mission
 * pair's range-rate over the *whole* scenario is often more informative to
 * scan freely than to only see at the live playhead) with a toggle back to
 * following the main scenario clock. Every figure comes straight from
 * domain/doppler.ts (rangeAndRangeRate / sampleRangeSeries — reused as-is,
 * no new geometry math). The canvas's per-pair cards additionally show
 * Δaltitude, bearing, a Doppler-shift-at-fc figure and a geometry-quality
 * badge; none of those are reproduced here because the domain model has no
 * receiver altitude field, no bearing calculation, and no carrier-frequency
 * association per receiver/mission pair to shift — adding them would mean
 * inventing values the backend doesn't provide.
 */
export function DopplerBlade({
  receivers,
  missions,
  scenarioTimeSeconds,
  maxSeconds,
  onClose,
}: {
  receivers: Receiver[];
  missions: DroneMission[];
  scenarioTimeSeconds: number;
  maxSeconds: number;
  onClose: () => void;
}) {
  const [linked, setLinked] = useState(true);
  const [scrubSeconds, setScrubSeconds] = useState(scenarioTimeSeconds);
  const t = linked ? scenarioTimeSeconds : scrubSeconds;

  const pairs = receivers.flatMap((receiver) => missions.map((mission) => ({ receiver, mission })));

  return (
    <Blade
      kicker="D · Sub-view of Spatial knowledge"
      title="Receiver geometry & Doppler overview"
      width={1080}
      onClose={onClose}
      headerExtra={
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ font: "400 11px/1 var(--mono)", color: "var(--ink-3)" }}>
            {linked ? "following main clock" : "independent scrub"}
          </span>
          <input
            type="range"
            min={0}
            max={maxSeconds}
            step={1}
            value={t}
            disabled={linked}
            onChange={(e) => setScrubSeconds(Number(e.target.value))}
            style={{ width: 200, accentColor: "var(--accent)" }}
          />
          <span style={{ font: "500 12px/1 var(--mono)", width: 44 }}>{fmtT(t)}</span>
          <button
            type="button"
            onClick={() => {
              // Going linked -> unlinked: start the independent scrub from
              // wherever the main clock currently is, not wherever it was
              // last time the blade was unlinked.
              if (linked) setScrubSeconds(scenarioTimeSeconds);
              setLinked((l) => !l);
            }}
            style={{
              height: 25,
              padding: "0 9px",
              background: linked ? "var(--accent-soft)" : "var(--surface)",
              border: "1px solid var(--line-2)",
              borderRadius: 2,
              cursor: "pointer",
              fontSize: 11.5,
              color: linked ? "var(--accent)" : "var(--ink-2)",
            }}
          >
            {linked ? "Linked" : "Unlinked"}
          </button>
        </div>
      }
    >
      {pairs.length === 0 ? (
        <div style={{ padding: "8px 0", fontSize: 12, color: "var(--ink-3)" }}>
          Add at least one receiver and one mission to see range/range-rate geometry.
        </div>
      ) : (
        <>
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fill, minmax(258px, 1fr))",
              gap: 11,
            }}
          >
            {pairs.map(({ receiver, mission }) => {
              const { rangeM, rangeRateMps } = rangeAndRangeRate(receiver, mission, t);
              const series = sampleRangeSeries(receiver, mission, maxSeconds);
              const color = colorForMission(missions, mission.id);
              const receding = rangeRateMps >= 0;
              const tone = receding ? "info" : "warn";
              const markPct = maxSeconds > 0 ? (t / maxSeconds) * 100 : 0;

              return (
                <div
                  key={`${receiver.id}:${mission.id}`}
                  style={{
                    border: "1px solid var(--line)",
                    borderRadius: 3,
                    background: "var(--surface)",
                    overflow: "hidden",
                  }}
                >
                  <div
                    style={{
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "space-between",
                      gap: 8,
                      padding: "7px 10px",
                      borderBottom: "1px solid var(--line)",
                      background: "var(--surface-2)",
                    }}
                  >
                    <div style={{ display: "flex", alignItems: "center", gap: 7, minWidth: 0 }}>
                      <span
                        aria-hidden
                        style={{
                          width: 7,
                          height: 7,
                          borderRadius: "50%",
                          background: color,
                          flex: "0 0 7px",
                        }}
                      />
                      <span style={{ font: "600 11.5px/1 var(--mono)" }}>
                        {receiver.name} · {mission.name}
                      </span>
                    </div>
                    <span
                      style={{
                        font: "500 10px/1.7 var(--mono)",
                        padding: "0 5px",
                        borderRadius: 2,
                        color: `var(--${tone}-fg)`,
                        background: `var(--${tone}-bg)`,
                        border: `1px solid var(--${tone}-bd)`,
                      }}
                    >
                      {receding ? "receding" : "closing"}
                    </span>
                  </div>
                  <div
                    style={{
                      padding: "9px 10px",
                      display: "grid",
                      gridTemplateColumns: "1fr 1fr",
                      gap: 8,
                    }}
                  >
                    <div>
                      <div
                        style={{
                          font: "500 9.5px/1.2 var(--mono)",
                          letterSpacing: "0.07em",
                          textTransform: "uppercase",
                          color: "var(--ink-3)",
                        }}
                      >
                        Slant range
                      </div>
                      <div style={{ font: "500 15px/1.4 var(--mono)" }}>
                        {(rangeM / 1000).toFixed(3)} km
                      </div>
                    </div>
                    <div>
                      <div
                        style={{
                          font: "500 9.5px/1.2 var(--mono)",
                          letterSpacing: "0.07em",
                          textTransform: "uppercase",
                          color: "var(--ink-3)",
                        }}
                      >
                        Range rate
                      </div>
                      <div style={{ font: "500 15px/1.4 var(--mono)", color: `var(--${tone}-fg)` }}>
                        {rangeRateMps >= 0 ? "+" : ""}
                        {rangeRateMps.toFixed(1)} m/s
                      </div>
                    </div>
                  </div>
                  <div
                    style={{
                      padding: "0 10px 9px",
                      display: "flex",
                      flexDirection: "column",
                      gap: 4,
                    }}
                  >
                    <div
                      style={{
                        display: "flex",
                        justifyContent: "space-between",
                        font: "400 9.5px/1 var(--mono)",
                        color: "var(--ink-3)",
                      }}
                    >
                      <span>range over T</span>
                    </div>
                    <svg
                      viewBox="0 0 100 28"
                      preserveAspectRatio="none"
                      style={{
                        width: "100%",
                        height: 30,
                        border: "1px solid var(--line)",
                        background: "var(--surface-2)",
                      }}
                    >
                      <polyline
                        points={sparklinePoints(series.map((s) => s.rangeM))}
                        style={{
                          fill: "none",
                          stroke: color,
                          strokeWidth: 1,
                          vectorEffect: "non-scaling-stroke",
                        }}
                      />
                      <line
                        x1={markPct}
                        y1={0}
                        x2={markPct}
                        y2={28}
                        style={{
                          stroke: "var(--accent)",
                          strokeWidth: 1,
                          vectorEffect: "non-scaling-stroke",
                        }}
                      />
                    </svg>
                    <div
                      style={{
                        display: "flex",
                        justifyContent: "space-between",
                        font: "400 9.5px/1 var(--mono)",
                        color: "var(--ink-3)",
                      }}
                    >
                      <span>range-rate over T</span>
                    </div>
                    <svg
                      viewBox="0 0 100 28"
                      preserveAspectRatio="none"
                      style={{
                        width: "100%",
                        height: 30,
                        border: "1px solid var(--line)",
                        background: "var(--surface-2)",
                      }}
                    >
                      <line
                        x1={0}
                        y1={14}
                        x2={100}
                        y2={14}
                        style={{
                          stroke: "var(--line-2)",
                          strokeWidth: 1,
                          vectorEffect: "non-scaling-stroke",
                        }}
                      />
                      <polyline
                        points={sparklinePoints(series.map((s) => s.rangeRateMps))}
                        style={{
                          fill: "none",
                          stroke: "var(--accent-2)",
                          strokeWidth: 1,
                          vectorEffect: "non-scaling-stroke",
                        }}
                      />
                      <line
                        x1={markPct}
                        y1={0}
                        x2={markPct}
                        y2={28}
                        style={{
                          stroke: "var(--accent)",
                          strokeWidth: 1,
                          vectorEffect: "non-scaling-stroke",
                        }}
                      />
                    </svg>
                  </div>
                </div>
              );
            })}
          </div>

          <div
            style={{
              border: "1px solid var(--line)",
              borderRadius: 3,
              background: "var(--surface)",
              overflow: "hidden",
            }}
          >
            <div
              style={{
                padding: "7px 12px",
                borderBottom: "1px solid var(--line)",
                background: "var(--surface-2)",
                font: "600 11px/1.2 var(--mono)",
                letterSpacing: "0.09em",
                textTransform: "uppercase",
                color: "var(--ink-3)",
              }}
            >
              Pair matrix at t = {fmtT(t)}
            </div>
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "1.4fr 1fr 1fr",
                padding: "5px 12px",
                background: "var(--surface-2)",
                borderBottom: "1px solid var(--line)",
                font: "500 10px/1 var(--mono)",
                letterSpacing: "0.06em",
                textTransform: "uppercase",
                color: "var(--ink-3)",
              }}
            >
              <div>Receiver ▸ mission</div>
              <div>Slant range</div>
              <div>Range rate</div>
            </div>
            {pairs.map(({ receiver, mission }) => {
              const { rangeM, rangeRateMps } = rangeAndRangeRate(receiver, mission, t);
              const color = colorForMission(missions, mission.id);
              const tone = rangeRateMps >= 0 ? "info" : "warn";
              return (
                <div
                  key={`${receiver.id}:${mission.id}`}
                  style={{
                    display: "grid",
                    gridTemplateColumns: "1.4fr 1fr 1fr",
                    padding: "var(--rp) 12px",
                    borderBottom: "1px solid var(--line)",
                    alignItems: "center",
                    font: "400 11.5px/1.4 var(--mono)",
                    color: "var(--ink-2)",
                  }}
                >
                  <div
                    style={{ color: "var(--ink)", display: "flex", alignItems: "center", gap: 7 }}
                  >
                    <span
                      aria-hidden
                      style={{ width: 6, height: 6, borderRadius: "50%", background: color }}
                    />
                    {receiver.name} ▸ {mission.name}
                  </div>
                  <div>{(rangeM / 1000).toFixed(3)} km</div>
                  <div style={{ color: `var(--${tone}-fg)` }}>
                    {rangeRateMps >= 0 ? "+" : ""}
                    {rangeRateMps.toFixed(1)} m/s
                  </div>
                </div>
              );
            })}
          </div>
        </>
      )}
    </Blade>
  );
}
