import { buildLinkTimelineRows, formatAxisTime } from "../../domain/signalTimeline";
import type { DroneMission, IQRecording } from "../../domain/types";
import type { Selection } from "../../state/selection";
import { useScenarioTime } from "../../state/scenarioTimeContext";
import { toneVars } from "../../styles/tokens";

const ROW_LABEL_WIDTH = 168;
const TRACK_HEIGHT = 78;

/** `oklch(0.6 0.15 245)` -> `oklch(0.6 0.15 245 / .16)` — a translucent fill of the same mission color used for the block's border. */
function withAlpha(oklch: string, alpha: number): string {
  return oklch.replace(/\)$/, ` / ${alpha})`);
}

/**
 * The Signal Knowledge Gantt timeline: one row per RF link, its emission
 * spans and authored frequency-change ticks laid out against the shared
 * 0..maxSeconds authoring axis, with a live playhead. Matches the ROGUE
 * Console design canvas's Signal Knowledge grid exactly (link identity +
 * band/behaviour on the left, a fixed-axis track on the right with a
 * background grid, emission blocks, channel/band-switch ticks and a
 * playhead line) — see domain/signalTimeline.ts for how each field maps
 * back to the real DroneRfLink/RfEmission/FrequencyBehaviour data.
 */
export function SignalTimeline({
  missions,
  maxSeconds,
  catalogue,
  selection,
  onSelect,
}: {
  missions: DroneMission[];
  maxSeconds: number;
  catalogue: IQRecording[];
  selection: Selection;
  onSelect: (selection: Selection) => void;
}) {
  const { scenarioTimeSeconds } = useScenarioTime();
  const rows = buildLinkTimelineRows(missions, maxSeconds, catalogue);
  const playPct = Math.min(100, (scenarioTimeSeconds / maxSeconds) * 100);

  if (rows.length === 0) {
    return (
      <div style={{ padding: "8px 12px", fontSize: 12, color: "var(--ink-3)" }}>
        No RF links in this scenario yet.
      </div>
    );
  }

  return (
    <div data-testid="signal-timeline">
      <div
        style={{
          display: "grid",
          gridTemplateColumns: `${ROW_LABEL_WIDTH}px minmax(0,1fr)`,
          borderBottom: "1px solid var(--line)",
          background: "var(--surface-2)",
          font: "500 10px/1 var(--mono)",
          letterSpacing: "0.06em",
          textTransform: "uppercase",
          color: "var(--ink-3)",
        }}
      >
        <div style={{ padding: "6px 10px", borderRight: "1px solid var(--line)" }}>
          RF link / mission
        </div>
        <div style={{ padding: "6px 10px", display: "flex", justifyContent: "space-between" }}>
          <span>{formatAxisTime(0)}</span>
          <span>{formatAxisTime(maxSeconds / 2)}</span>
          <span>{formatAxisTime(maxSeconds)}</span>
        </div>
      </div>
      {rows.map((row) => {
        const isSelected =
          selection?.kind === "rfLink" &&
          selection.missionId === row.missionId &&
          selection.linkId === row.linkId;
        const behTone = toneVars(row.behaviourTone);
        return (
          <div
            key={row.linkId}
            data-testid={`signal-timeline-row-${row.linkId}`}
            onClick={() =>
              onSelect({ kind: "rfLink", missionId: row.missionId, linkId: row.linkId })
            }
            style={{
              display: "grid",
              gridTemplateColumns: `${ROW_LABEL_WIDTH}px minmax(0,1fr)`,
              borderBottom: "1px solid var(--line)",
              background: isSelected ? "var(--surface-3)" : "var(--surface)",
              cursor: "pointer",
            }}
          >
            <div style={{ padding: "7px 10px", borderRight: "1px solid var(--line)", minWidth: 0 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <span
                  aria-hidden
                  style={{
                    width: 7,
                    height: 7,
                    borderRadius: "50%",
                    background: row.color,
                    flex: "0 0 7px",
                  }}
                />
                <span style={{ fontWeight: 600, fontSize: 12, textTransform: "uppercase" }}>
                  {row.role}
                </span>
                <span
                  style={{
                    font: "500 10px/1.6 var(--mono)",
                    padding: "0 4px",
                    borderRadius: 2,
                    color: "var(--mute-fg)",
                    background: "var(--mute-bg)",
                    border: "1px solid var(--mute-bd)",
                  }}
                >
                  {row.linkId.slice(0, 8)}
                </span>
              </div>
              <div
                style={{ font: "400 10.5px/1.5 var(--mono)", color: "var(--ink-3)", marginTop: 2 }}
              >
                {row.missionName}
              </div>
              <div style={{ font: "400 10.5px/1.5 var(--mono)", color: "var(--ink-2)" }}>
                {row.bandLabel}
              </div>
              <div style={{ font: "400 10.5px/1.5 var(--mono)", color: "var(--ink-3)" }}>
                ch {row.channelsLabel}
              </div>
              <div style={{ marginTop: 3 }}>
                <span
                  style={{
                    display: "inline-flex",
                    font: "500 10px/1.6 var(--mono)",
                    padding: "0 5px",
                    borderRadius: 2,
                    color: behTone.fg,
                    background: behTone.bg,
                    border: `1px solid ${behTone.bd}`,
                  }}
                >
                  {row.behaviourMode}
                </span>
              </div>
            </div>
            <div
              style={{
                position: "relative",
                height: TRACK_HEIGHT,
                backgroundImage:
                  "repeating-linear-gradient(90deg, transparent 0 9.99%, var(--line) 9.99% 10%)",
              }}
            >
              {row.emissions.map((e, i) => (
                <div
                  key={e.emissionId}
                  title={e.title}
                  style={{
                    position: "absolute",
                    top: 8 + i * 24,
                    left: `${e.leftPct}%`,
                    width: `${e.widthPct}%`,
                    height: 20,
                    borderRadius: 2,
                    background: e.durationResolved ? withAlpha(row.color, 0.16) : "var(--mute-bg)",
                    border: `1px solid ${e.durationResolved ? row.color : "var(--line-2)"}`,
                    display: "flex",
                    alignItems: "center",
                    padding: "0 5px",
                    overflow: "hidden",
                  }}
                >
                  <span
                    style={{
                      font: "500 10px/1 var(--mono)",
                      color: "var(--ink)",
                      whiteSpace: "nowrap",
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                    }}
                  >
                    {e.label}
                  </span>
                </div>
              ))}
              {row.changes.map((c) => (
                <div
                  key={c.key}
                  title={c.title}
                  style={{
                    position: "absolute",
                    top: c.isBandSwitch ? 56 : 58,
                    left: `${c.leftPct}%`,
                    transform: "translateX(-50%)",
                    display: "flex",
                    flexDirection: "column",
                    alignItems: "center",
                    gap: 2,
                  }}
                >
                  <span
                    style={{
                      width: c.isBandSwitch ? 9 : 6,
                      height: c.isBandSwitch ? 9 : 6,
                      background: c.isBandSwitch ? "var(--bad-fg)" : "var(--accent)",
                      transform: c.isBandSwitch ? "rotate(45deg)" : undefined,
                      display: "block",
                    }}
                  />
                  <span
                    style={{
                      font: "500 9.5px/1 var(--mono)",
                      color: "var(--ink-3)",
                      whiteSpace: "nowrap",
                    }}
                  >
                    {c.label}
                  </span>
                </div>
              ))}
              <div
                style={{
                  position: "absolute",
                  top: 0,
                  bottom: 0,
                  left: `${playPct}%`,
                  width: 1,
                  background: "var(--accent)",
                }}
              />
            </div>
          </div>
        );
      })}
    </div>
  );
}
