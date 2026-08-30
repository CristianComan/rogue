import type {
  DroneRfLink,
  FrequencySwitchingMode,
  FrequencyTransitionType,
  IQRecording,
  RfEmission,
  RfLinkRole,
  ScriptedFrequencyChange,
  TimingSyncClass,
} from "../../domain/types";
import { NumberField, SelectField, TextField } from "./fields";
import { RecordingPicker } from "./RecordingPicker";

const ROLES: readonly RfLinkRole[] = ["c2", "telemetry", "video", "data"];
const MODES: readonly FrequencySwitchingMode[] = [
  "scripted",
  "mission_triggered",
  "probabilistic_adaptive",
  "external_state_triggered",
];
const TRANSITION_TYPES: readonly FrequencyTransitionType[] = ["channel_switch", "band_switch"];
// "none" is a UI-only sentinel for required_sync_class's null case — never
// sent to the backend as a literal TimingSyncClass value.
const SYNC_CLASS_OPTIONS: readonly (TimingSyncClass | "none")[] = [
  "none",
  "l0_simulated",
  "l1_software_barrier",
  "l2_scheduled_local",
  "l3_shared_reference",
  "l4_measured",
];

export interface RfLinkFormProps {
  link: DroneRfLink;
  onChange: (link: DroneRfLink) => void;
  onDelete: () => void;
  /** The owning mission's recording catalogue + platform, for RecordingPicker. */
  catalogue: IQRecording[];
  platformName: string;
}

/**
 * Field-level validation stays minimal here — the backend's /validate
 * endpoint is the source of truth for mode/field consistency (e.g.
 * "scripted mode requires scripted_changes"), not a client-side replica of
 * every Pydantic model validator.
 */
export function RfLinkForm({ link, onChange, onDelete, catalogue, platformName }: RfLinkFormProps) {
  const mode = link.frequency_behaviour.mode;

  function updateScriptedChange(index: number, patch: Partial<ScriptedFrequencyChange>) {
    const next = link.frequency_behaviour.scripted_changes.map((c, i) =>
      i === index ? { ...c, ...patch } : c,
    );
    onChange({
      ...link,
      frequency_behaviour: { ...link.frequency_behaviour, scripted_changes: next },
    });
  }

  function addScriptedChange() {
    const next: ScriptedFrequencyChange = {
      at_offset: "PT0S",
      frequency_hz: link.band.freq_min_hz,
      transition_type: "channel_switch",
    };
    onChange({
      ...link,
      frequency_behaviour: {
        ...link.frequency_behaviour,
        scripted_changes: [...link.frequency_behaviour.scripted_changes, next],
      },
    });
  }

  function removeScriptedChange(index: number) {
    onChange({
      ...link,
      frequency_behaviour: {
        ...link.frequency_behaviour,
        scripted_changes: link.frequency_behaviour.scripted_changes.filter((_, i) => i !== index),
      },
    });
  }

  function updateEmission(index: number, patch: Partial<RfEmission>) {
    onChange({
      ...link,
      emissions: link.emissions.map((e, i) => (i === index ? { ...e, ...patch } : e)),
    });
  }

  function addEmission() {
    const newEmission: RfEmission = {
      id: crypto.randomUUID(),
      recording: { recording_id: "", version: 1, note: null },
      start_offset: "PT0S",
      duration_override: null,
      gain_offset_db: 0,
      loop: false,
      notes: null,
    };
    onChange({ ...link, emissions: [...link.emissions, newEmission] });
  }

  function removeEmission(index: number) {
    onChange({ ...link, emissions: link.emissions.filter((_, i) => i !== index) });
  }

  function toggleSilence(index: number, silent: boolean) {
    const emission = link.emissions[index];
    if (silent) {
      // A silence span has no recording to derive a length from — the
      // backend requires duration_override whenever recording is null.
      updateEmission(index, {
        recording: null,
        duration_override: emission.duration_override ?? "PT1S",
      });
    } else {
      updateEmission(index, { recording: { recording_id: "", version: 1, note: null } });
    }
  }

  function setResourcePreference(enabled: boolean) {
    onChange({
      ...link,
      resource_preference: enabled
        ? { preferred_agent_tags: [], required_sync_class: null, notes: null }
        : null,
    });
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      <div style={{ display: "flex", gap: 8 }}>
        <SelectField
          label="Role"
          value={link.role}
          options={ROLES}
          onChange={(role) => onChange({ ...link, role })}
        />
        <button type="button" onClick={onDelete}>
          Delete link
        </button>
      </div>

      <fieldset style={{ border: "1px solid #ccc" }}>
        <legend>Band</legend>
        <div style={{ display: "flex", gap: 8 }}>
          <NumberField
            label="Min (Hz)"
            value={link.band.freq_min_hz}
            onChange={(freq_min_hz) => onChange({ ...link, band: { ...link.band, freq_min_hz } })}
          />
          <NumberField
            label="Max (Hz)"
            value={link.band.freq_max_hz}
            onChange={(freq_max_hz) => onChange({ ...link, band: { ...link.band, freq_max_hz } })}
          />
        </div>
      </fieldset>

      <fieldset style={{ border: "1px solid #ccc" }}>
        <legend>Frequency behaviour</legend>
        <SelectField
          label="Mode"
          value={mode}
          options={MODES}
          onChange={(newMode) =>
            onChange({
              ...link,
              frequency_behaviour: { ...link.frequency_behaviour, mode: newMode },
            })
          }
        />
        {mode === "scripted" && (
          <div style={{ display: "flex", flexDirection: "column", gap: 6, marginTop: 8 }}>
            {link.frequency_behaviour.scripted_changes.map((change, i) => (
              <div key={i} data-testid={`scripted-change-${i}`} style={{ display: "flex", gap: 8 }}>
                <TextField
                  label="At offset"
                  value={change.at_offset}
                  onChange={(at_offset) => updateScriptedChange(i, { at_offset })}
                />
                <NumberField
                  label="Frequency (Hz)"
                  value={change.frequency_hz}
                  onChange={(frequency_hz) => updateScriptedChange(i, { frequency_hz })}
                />
                <SelectField
                  label="Transition"
                  value={change.transition_type}
                  options={TRANSITION_TYPES}
                  onChange={(transition_type) => updateScriptedChange(i, { transition_type })}
                />
                <button type="button" onClick={() => removeScriptedChange(i)}>
                  Remove
                </button>
              </div>
            ))}
            <button type="button" onClick={addScriptedChange} style={{ alignSelf: "flex-start" }}>
              + Scripted change
            </button>
          </div>
        )}
      </fieldset>

      <fieldset style={{ border: "1px solid #ccc" }}>
        <legend>Emissions</legend>
        <p style={{ fontSize: 11, color: "#4c5c5e", margin: "0 0 8px" }}>
          Start offset + duration place a recording within this mission's trajectory — an empty
          duration plays the full recording. Mark a span "Silence" to author the link as
          deliberately off-air for that span (a duration is then required, since there's no
          recording to derive a length from). Background-kind recordings are labeled "· background"
          in the picker.
        </p>
        {link.emissions.map((emission, i) => {
          const isSilent = emission.recording === null;
          return (
            <div
              key={emission.id}
              data-testid={`emission-${i}`}
              style={{
                display: "flex",
                flexWrap: "wrap",
                gap: 8,
                marginBottom: 6,
                alignItems: "flex-end",
              }}
            >
              <label style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 12 }}>
                <input
                  type="checkbox"
                  checked={isSilent}
                  onChange={(e) => toggleSilence(i, e.target.checked)}
                />
                Silence
              </label>
              {!isSilent && emission.recording && (
                <>
                  <RecordingPicker
                    recordings={catalogue}
                    value={emission.recording.recording_id}
                    preferredPlatform={platformName}
                    onChange={(recording_id) =>
                      updateEmission(i, {
                        recording: { ...emission.recording!, recording_id },
                      })
                    }
                  />
                  <NumberField
                    label="Version"
                    value={emission.recording.version}
                    onChange={(version) =>
                      updateEmission(i, { recording: { ...emission.recording!, version } })
                    }
                  />
                </>
              )}
              <TextField
                label="Start offset"
                value={emission.start_offset}
                onChange={(start_offset) => updateEmission(i, { start_offset })}
              />
              <TextField
                label={isSilent ? "Duration (required)" : "Duration override"}
                value={emission.duration_override ?? ""}
                onChange={(v) => updateEmission(i, { duration_override: v || null })}
              />
              <NumberField
                label="Gain (dB)"
                value={emission.gain_offset_db}
                onChange={(gain_offset_db) => updateEmission(i, { gain_offset_db })}
              />
              <label style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 12 }}>
                <input
                  type="checkbox"
                  checked={emission.loop}
                  onChange={(e) => updateEmission(i, { loop: e.target.checked })}
                />
                Loop
              </label>
              <button type="button" onClick={() => removeEmission(i)}>
                Remove
              </button>
            </div>
          );
        })}
        <button type="button" onClick={addEmission} style={{ alignSelf: "flex-start" }}>
          + Emission
        </button>
      </fieldset>

      <fieldset style={{ border: "1px solid #ccc" }}>
        <legend>Resource preference (non-binding)</legend>
        <p style={{ fontSize: 11, color: "#4c5c5e", margin: "0 0 8px" }}>
          A preference only — never a device binding (CLAUDE.md rule 1). Actual SDR/channel
          assignment happens at run preparation and is recorded in the immutable run manifest, not
          here.
        </p>
        <label style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 12 }}>
          <input
            type="checkbox"
            checked={link.resource_preference !== null}
            onChange={(e) => setResourcePreference(e.target.checked)}
          />
          Set a resource preference for this link
        </label>
        {link.resource_preference && (
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 8 }}>
            <TextField
              label="Preferred agent tags (comma separated)"
              value={link.resource_preference.preferred_agent_tags.join(", ")}
              onChange={(v) =>
                onChange({
                  ...link,
                  resource_preference: {
                    ...link.resource_preference!,
                    preferred_agent_tags: v
                      .split(",")
                      .map((tag) => tag.trim())
                      .filter(Boolean),
                  },
                })
              }
            />
            <SelectField
              label="Required sync class"
              value={link.resource_preference.required_sync_class ?? "none"}
              options={SYNC_CLASS_OPTIONS}
              onChange={(v) =>
                onChange({
                  ...link,
                  resource_preference: {
                    ...link.resource_preference!,
                    required_sync_class: v === "none" ? null : v,
                  },
                })
              }
            />
            <TextField
              label="Notes"
              value={link.resource_preference.notes ?? ""}
              onChange={(v) =>
                onChange({
                  ...link,
                  resource_preference: { ...link.resource_preference!, notes: v || null },
                })
              }
            />
          </div>
        )}
      </fieldset>
    </div>
  );
}
