import type { ScenarioContent, ValidationFinding } from "../../domain/types";
import type { Selection } from "../../state/selection";

export interface ValidationFindingsPanelProps {
  findings: ValidationFinding[];
  content: ScenarioContent;
  onSelectPath?: (selection: Selection) => void;
}

/**
 * Best-effort path -> selection resolution (e.g.
 * "missions[0].rf_links[1].emissions[0]..." -> that mission, by resolving
 * the array index against the current content). Good enough to jump the
 * properties pane to the right object; not a full JSON-pointer resolver.
 */
function parsePathToSelection(path: string, content: ScenarioContent): Selection {
  const missionMatch = /^missions\[(\d+)\]/.exec(path);
  if (missionMatch) {
    const mission = content.missions[Number(missionMatch[1])];
    return mission ? { kind: "mission", id: mission.id } : null;
  }
  const zoneMatch = /^zones\[(\d+)\]/.exec(path);
  if (zoneMatch) {
    const zone = content.zones[Number(zoneMatch[1])];
    return zone ? { kind: "zone", id: zone.id } : null;
  }
  const receiverMatch = /^receivers\[(\d+)\]/.exec(path);
  if (receiverMatch) {
    const receiver = content.receivers[Number(receiverMatch[1])];
    return receiver ? { kind: "receiver", id: receiver.id } : null;
  }
  return null;
}

export function ValidationFindingsPanel({
  findings,
  content,
  onSelectPath,
}: ValidationFindingsPanelProps) {
  if (findings.length === 0) {
    return <div style={{ padding: 8, fontSize: 12, color: "#2c7a63" }}>No findings.</div>;
  }

  const blocking = findings.filter((f) => f.severity === "blocking");
  const warnings = findings.filter((f) => f.severity === "warning");

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8, padding: 8 }}>
      {blocking.length > 0 && (
        <div>
          <div style={{ fontSize: 11, fontWeight: 600, color: "#a3311f" }}>
            Blocking ({blocking.length})
          </div>
          {blocking.map((f, i) => (
            <FindingRow
              key={i}
              finding={f}
              onClick={() => onSelectPath?.(parsePathToSelection(f.path, content))}
            />
          ))}
        </div>
      )}
      {warnings.length > 0 && (
        <div>
          <div style={{ fontSize: 11, fontWeight: 600, color: "#a34b1f" }}>
            Warnings ({warnings.length})
          </div>
          {warnings.map((f, i) => (
            <FindingRow
              key={i}
              finding={f}
              onClick={() => onSelectPath?.(parsePathToSelection(f.path, content))}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function FindingRow({ finding, onClick }: { finding: ValidationFinding; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      style={{
        display: "block",
        width: "100%",
        textAlign: "left",
        fontSize: 12,
        padding: "4px 6px",
        border: "1px solid #eee",
        background: "none",
        cursor: "pointer",
      }}
      title={finding.path}
    >
      <code style={{ fontSize: 10 }}>{finding.code}</code>: {finding.message}
    </button>
  );
}
