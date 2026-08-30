import type { IQRecording } from "../../domain/types";

const CUSTOM_VALUE = "__custom__";

export interface RecordingPickerProps {
  recordings: IQRecording[];
  value: string;
  onChange: (recordingId: string) => void;
  /**
   * When given, catalogue entries whose provenance mentions this platform
   * (case-insensitive substring — drone-corpus ingest's provenance strings
   * look like "campaign=..., drone_id=00, platform=DJI Mavic 2 Pro, ...",
   * scripts/ingest_drone_corpus.py) are grouped ahead of the rest. Never a
   * hard filter: a scenario with no matching recordings should still be
   * able to pick from everything else.
   */
  preferredPlatform?: string;
}

function labelFor(recording: IQRecording): string {
  const shortId = recording.id.slice(0, 8);
  const kindSuffix = recording.kind === "background" ? " · background" : "";
  const platform = recording.provenance?.match(/platform=([^,]+)/)?.[1]?.trim();
  if (platform) return `${platform} (${shortId})${kindSuffix}`;
  if (recording.provenance) return `${recording.provenance.slice(0, 40)} (${shortId})${kindSuffix}`;
  return `${recording.id}${kindSuffix}`;
}

/**
 * Replaces a bare recording-id TextField wherever a scenario references a
 * catalogue entry (RecordingsListEditor, RfLinkForm's emissions) — the
 * catalogue (GET /recordings, M4) is fetched once by EditorLayout and
 * passed down, not re-fetched per picker. Falls back to a plain text input
 * for a value that isn't in the fetched list (a legacy/manually-entered id,
 * or the catalogue fetch failing/truncating), so this never blocks entering
 * an id the picker doesn't happen to know about.
 */
export function RecordingPicker({
  recordings,
  value,
  onChange,
  preferredPlatform,
}: RecordingPickerProps) {
  const matching = preferredPlatform
    ? recordings.filter((r) =>
        r.provenance?.toLowerCase().includes(preferredPlatform.toLowerCase()),
      )
    : [];
  const matchingIds = new Set(matching.map((r) => r.id));
  const others = recordings.filter((r) => !matchingIds.has(r.id));
  const isCustom = value !== "" && !recordings.some((r) => r.id === value);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
      <label style={{ display: "flex", flexDirection: "column", gap: 2, fontSize: 12 }}>
        Recording
        <select
          value={isCustom ? CUSTOM_VALUE : value}
          onChange={(e) => onChange(e.target.value === CUSTOM_VALUE ? "" : e.target.value)}
        >
          <option value="" disabled>
            Select a recording…
          </option>
          {matching.length > 0 && (
            <optgroup label={`Matching platform: ${preferredPlatform}`}>
              {matching.map((r) => (
                <option key={r.id} value={r.id}>
                  {labelFor(r)}
                </option>
              ))}
            </optgroup>
          )}
          <optgroup label={matching.length > 0 ? "All recordings" : "Recordings"}>
            {others.map((r) => (
              <option key={r.id} value={r.id}>
                {labelFor(r)}
              </option>
            ))}
          </optgroup>
          <option value={CUSTOM_VALUE}>Custom UUID…</option>
        </select>
      </label>
      {isCustom && (
        <input
          type="text"
          value={value}
          placeholder="recording UUID"
          onChange={(e) => onChange(e.target.value)}
        />
      )}
    </div>
  );
}
