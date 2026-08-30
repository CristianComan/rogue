import type { Receiver } from "../../domain/types";
import type { Selection } from "../../state/selection";

export interface ReceiversListEditorProps {
  receivers: Receiver[];
  selection: Selection;
  onSelect: (selection: Selection) => void;
}

/**
 * An always-visible list of the scenario's receivers, alongside
 * ZonesListEditor/MissionsListEditor — a receiver otherwise only exists as a
 * map-clickable point, so one off-screen or under a drone track is hard to
 * reach. Not an inline editor: receivers already have real create (toolbar)/
 * select (map or here)/edit (ReceiverForm)/delete (ReceiverForm) — this only
 * adds the missing "see everything" affordance.
 */
export function ReceiversListEditor({ receivers, selection, onSelect }: ReceiversListEditorProps) {
  return (
    <div
      data-testid="receivers-panel"
      style={{ display: "flex", flexDirection: "column", gap: 4, padding: 12 }}
    >
      <strong style={{ fontSize: 12 }}>Receivers</strong>
      {receivers.length === 0 && (
        <span style={{ fontSize: 12, color: "#4c5c5e" }}>No receivers in this scenario.</span>
      )}
      {receivers.map((receiver) => {
        const isSelected = selection?.kind === "receiver" && selection.id === receiver.id;
        return (
          <button
            key={receiver.id}
            type="button"
            data-testid={`receivers-panel-row-${receiver.id}`}
            onClick={() => onSelect({ kind: "receiver", id: receiver.id })}
            style={{
              textAlign: "left",
              fontSize: 12,
              padding: "4px 6px",
              background: isSelected ? "#e4ebe8" : "transparent",
              border: "1px solid #ccc",
              cursor: "pointer",
            }}
          >
            {receiver.name} · {receiver.receiver_type}
          </button>
        );
      })}
    </div>
  );
}
