import type {
  DroneMission,
  DroneRfLink,
  IQRecording,
  MissionStartPolicy,
  MissionTemplate,
  PlatformCategory,
} from "../../domain/types";
import { NumberField, SelectField, TextField } from "./fields";
import { RfLinkForm } from "./RfLinkForm";
import { WaypointListEditor } from "./WaypointListEditor";

const PLATFORM_CATEGORIES: readonly PlatformCategory[] = [
  "multirotor",
  "fixed_wing",
  "vtol",
  "other",
];
const TEMPLATES: readonly MissionTemplate[] = [
  "waypoint_transit",
  "orbit",
  "racetrack",
  "grid_search",
  "perimeter_patrol",
  "loiter_then_depart",
  "swarm_staggered_arrival",
  "scripted_track",
];
const START_POLICIES: readonly MissionStartPolicy[] = [
  "at_scenario_start",
  "at_time_offset",
  "on_event",
  "manual",
];

export interface MissionFormProps {
  mission: DroneMission;
  onChange: (mission: DroneMission) => void;
  onDelete: () => void;
  catalogue: IQRecording[];
}

export function MissionForm({ mission, onChange, onDelete, catalogue }: MissionFormProps) {
  function addRfLink() {
    const newLink: DroneRfLink = {
      id: crypto.randomUUID(),
      role: "c2",
      band: { freq_min_hz: 2_400_000_000, freq_max_hz: 2_483_500_000, allowed_channels_hz: [] },
      frequency_behaviour: {
        mode: "scripted",
        scripted_changes: [
          { at_offset: "PT0S", frequency_hz: 2_412_000_000, transition_type: "channel_switch" },
        ],
        mission_trigger_anchor: null,
        random_seed: null,
        mean_dwell_s: null,
        external_trigger_reference: null,
      },
      emissions: [],
      resource_preference: null,
    };
    onChange({ ...mission, rf_links: [...mission.rf_links, newLink] });
  }

  function updateRfLink(index: number, link: DroneRfLink) {
    onChange({ ...mission, rf_links: mission.rf_links.map((l, i) => (i === index ? link : l)) });
  }

  function removeRfLink(index: number) {
    onChange({ ...mission, rf_links: mission.rf_links.filter((_, i) => i !== index) });
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12, padding: 16 }}>
      <h3 style={{ margin: 0 }}>Mission</h3>
      <TextField
        label="Name"
        value={mission.name}
        onChange={(name) => onChange({ ...mission, name })}
      />

      <fieldset style={{ border: "1px solid #ccc" }}>
        <legend>Platform</legend>
        <TextField
          label="Name"
          value={mission.platform.name}
          onChange={(name) => onChange({ ...mission, platform: { ...mission.platform, name } })}
        />
        <SelectField
          label="Category"
          value={mission.platform.category}
          options={PLATFORM_CATEGORIES}
          onChange={(category) =>
            onChange({ ...mission, platform: { ...mission.platform, category } })
          }
        />
        <NumberField
          label="Max speed (m/s)"
          value={mission.platform.max_speed_mps}
          onChange={(max_speed_mps) =>
            onChange({ ...mission, platform: { ...mission.platform, max_speed_mps } })
          }
        />
      </fieldset>

      <fieldset style={{ border: "1px solid #ccc" }}>
        <legend>Start</legend>
        <SelectField
          label="Policy"
          value={mission.start_policy}
          options={START_POLICIES}
          onChange={(start_policy) =>
            onChange({
              ...mission,
              start_policy,
              start_time_offset: start_policy === "at_time_offset" ? "PT0S" : null,
            })
          }
        />
        {mission.start_policy === "at_time_offset" && (
          <TextField
            label="Offset (ISO8601 duration)"
            value={mission.start_time_offset ?? "PT0S"}
            onChange={(start_time_offset) => onChange({ ...mission, start_time_offset })}
          />
        )}
      </fieldset>

      <fieldset style={{ border: "1px solid #ccc" }}>
        <legend>Trajectory</legend>
        <SelectField
          label="Template"
          value={mission.trajectory.template}
          options={TEMPLATES}
          onChange={(template) =>
            onChange({ ...mission, trajectory: { ...mission.trajectory, template } })
          }
        />
        <NumberField
          label="Default speed (m/s)"
          value={mission.trajectory.default_speed_mps}
          onChange={(default_speed_mps) =>
            onChange({ ...mission, trajectory: { ...mission.trajectory, default_speed_mps } })
          }
        />
        {mission.trajectory.template === "orbit" && (
          <NumberField
            label="Radius (m)"
            value={mission.trajectory.template_parameters.radius_m ?? 100}
            onChange={(radius_m) =>
              onChange({
                ...mission,
                trajectory: {
                  ...mission.trajectory,
                  template_parameters: { ...mission.trajectory.template_parameters, radius_m },
                },
              })
            }
          />
        )}
        <div style={{ marginTop: 8 }}>
          <WaypointListEditor
            waypoints={mission.trajectory.waypoints}
            onChange={(waypoints) =>
              onChange({ ...mission, trajectory: { ...mission.trajectory, waypoints } })
            }
          />
        </div>
      </fieldset>

      <fieldset style={{ border: "1px solid #ccc" }}>
        <legend>RF links</legend>
        {mission.rf_links.map((link, i) => (
          <div
            key={link.id}
            style={{ borderBottom: "1px solid #eee", paddingBottom: 8, marginBottom: 8 }}
          >
            <RfLinkForm
              link={link}
              onChange={(updated) => updateRfLink(i, updated)}
              onDelete={() => removeRfLink(i)}
              catalogue={catalogue}
              platformName={mission.platform.name}
            />
          </div>
        ))}
        <button type="button" onClick={addRfLink} style={{ alignSelf: "flex-start" }}>
          + RF link
        </button>
      </fieldset>

      <button type="button" onClick={onDelete} style={{ alignSelf: "flex-start" }}>
        Delete mission
      </button>
    </div>
  );
}
