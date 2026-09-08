import { flattenLinks } from "../../domain/signalOverview";
import type { DroneMission } from "../../domain/types";
import type { Selection } from "../../state/selection";
import { monoFontStack, sectionHeadingStyle } from "../../styles/tokens";

function mhz(hz: number): string {
  return (hz / 1e6).toFixed(3);
}

const COLUMNS = ["Mission", "Role", "Band", "Current freq", "Behaviour", "Emissions"];

/**
 * One row per RF link across *all* missions, flattened by
 * domain/signalOverview.ts — the cross-mission view Signal Knowledge needs
 * that nested per-mission editing (MissionForm -> RfLinkForm) doesn't give
 * you. Selecting a row reuses the existing {kind:"rfLink"} selection variant
 * (state/selection.ts), which PropertiesPane already routes to MissionForm.
 */
export function SignalLinksListEditor({
  missions,
  scenarioTimeSeconds,
  selection,
  onSelect,
}: {
  missions: DroneMission[];
  scenarioTimeSeconds: number;
  selection: Selection;
  onSelect: (selection: Selection) => void;
}) {
  const rows = flattenLinks(missions, scenarioTimeSeconds);

  return (
    <div data-testid="signal-links-panel" style={{ fontFamily: monoFontStack }}>
      {rows.length === 0 ? (
        <div style={{ padding: "8px 12px", fontSize: 12, color: "#4c5c5e" }}>
          No RF links in this scenario yet.
        </div>
      ) : (
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
          <thead>
            <tr>
              {COLUMNS.map((h) => (
                <th
                  key={h}
                  style={{ ...sectionHeadingStyle, textAlign: "left", padding: "4px 8px" }}
                >
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => {
              const isSelected =
                selection?.kind === "rfLink" &&
                selection.missionId === row.missionId &&
                selection.linkId === row.linkId;
              return (
                <tr
                  key={row.linkId}
                  data-testid={`signal-links-row-${row.linkId}`}
                  onClick={() =>
                    onSelect({ kind: "rfLink", missionId: row.missionId, linkId: row.linkId })
                  }
                  style={{
                    cursor: "pointer",
                    background: isSelected ? "#e4ebe8" : "transparent",
                  }}
                >
                  <td style={{ padding: "4px 8px" }}>{row.missionName}</td>
                  <td style={{ padding: "4px 8px", textTransform: "uppercase" }}>{row.role}</td>
                  <td style={{ padding: "4px 8px" }}>
                    {mhz(row.freqMinHz)}–{mhz(row.freqMaxHz)} MHz
                  </td>
                  <td style={{ padding: "4px 8px" }}>{mhz(row.currentFrequencyHz)} MHz</td>
                  <td style={{ padding: "4px 8px" }}>{row.behaviourMode}</td>
                  <td style={{ padding: "4px 8px" }}>{row.emissionCount}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </div>
  );
}
