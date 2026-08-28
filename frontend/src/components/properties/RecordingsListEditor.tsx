import type { RecordingReference } from "../../domain/types";
import { NumberField, TextField } from "./fields";

export interface RecordingsListEditorProps {
  recordings: RecordingReference[];
  onChange: (recordings: RecordingReference[]) => void;
}

/**
 * A flat add/remove list, not selection-driven (a RecordingReference has
 * no natural map representation) — so RfEmissions have something valid to
 * point at and /validate doesn't immediately flag dangling_recording_
 * reference. No catalogue browsing yet (M4).
 */
export function RecordingsListEditor({ recordings, onChange }: RecordingsListEditorProps) {
  function updateAt(index: number, patch: Partial<RecordingReference>) {
    onChange(recordings.map((r, i) => (i === index ? { ...r, ...patch } : r)));
  }

  function removeAt(index: number) {
    onChange(recordings.filter((_, i) => i !== index));
  }

  function add() {
    onChange([...recordings, { recording_id: crypto.randomUUID(), version: 1, note: null }]);
  }

  return (
    <div
      data-testid="recordings-panel"
      style={{ display: "flex", flexDirection: "column", gap: 8, padding: 12 }}
    >
      <strong style={{ fontSize: 12 }}>Recordings</strong>
      {recordings.map((r, i) => (
        <div key={i} style={{ display: "flex", gap: 8, alignItems: "flex-end" }}>
          <TextField
            label="Recording ID"
            value={r.recording_id}
            onChange={(recording_id) => updateAt(i, { recording_id })}
          />
          <NumberField
            label="Version"
            value={r.version}
            onChange={(version) => updateAt(i, { version })}
          />
          <button type="button" onClick={() => removeAt(i)}>
            Remove
          </button>
        </div>
      ))}
      <button type="button" onClick={add} style={{ alignSelf: "flex-start" }}>
        + Recording
      </button>
    </div>
  );
}
