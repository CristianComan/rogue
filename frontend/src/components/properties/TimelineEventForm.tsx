import type {
  AbsoluteTimelineEvent,
  DroneMission,
  MissionRelativeAnchor,
  MissionRelativeTimelineEvent,
  TimelineEvent,
} from "../../domain/types";
import { NumberField, SelectField, TextField } from "./fields";

const ANCHORS: readonly MissionRelativeAnchor[] = [
  "mission_start",
  "waypoint",
  "area_entry",
  "phase_completion",
];

export interface TimelineEventFormProps {
  event: TimelineEvent;
  missions: DroneMission[];
  onChange: (event: TimelineEvent) => void;
  onDelete: () => void;
}

/**
 * Only absolute and mission_relative events are creatable/editable here —
 * they're the two kinds the M3 mission-time evaluator can place on the
 * timeline meaningfully. manual_gated/external/safety events (e.g. from a
 * cloned scenario) are shown read-only elsewhere, not via this form.
 */
export function TimelineEventForm({ event, missions, onChange, onDelete }: TimelineEventFormProps) {
  if (event.kind !== "absolute" && event.kind !== "mission_relative") {
    return (
      <div style={{ padding: 16 }}>
        <h3>Timeline event ({event.kind})</h3>
        <p style={{ fontSize: 12, color: "#4c5c5e" }}>
          This event kind isn't editable in this milestone — shown read-only.
        </p>
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10, padding: 16 }}>
      <h3 style={{ margin: 0 }}>Timeline event</h3>
      <TextField
        label="Label"
        value={event.label ?? ""}
        onChange={(label) => onChange({ ...event, label: label || null } as TimelineEvent)}
      />
      {event.kind === "absolute" ? (
        <TextField
          label="Scenario time offset (ISO8601 duration)"
          value={event.scenario_time_offset}
          onChange={(scenario_time_offset) =>
            onChange({ ...event, scenario_time_offset } as AbsoluteTimelineEvent)
          }
        />
      ) : (
        <MissionRelativeFields event={event} missions={missions} onChange={onChange} />
      )}
      <button type="button" onClick={onDelete} style={{ alignSelf: "flex-start" }}>
        Delete event
      </button>
    </div>
  );
}

function MissionRelativeFields({
  event,
  missions,
  onChange,
}: {
  event: MissionRelativeTimelineEvent;
  missions: DroneMission[];
  onChange: (event: TimelineEvent) => void;
}) {
  return (
    <>
      <SelectField
        label="Mission"
        value={event.mission_id}
        options={missions.map((m) => m.id)}
        onChange={(mission_id) => onChange({ ...event, mission_id })}
      />
      <SelectField
        label="Anchor"
        value={event.anchor}
        options={ANCHORS}
        onChange={(anchor) => onChange({ ...event, anchor })}
      />
      {event.anchor === "waypoint" && (
        <NumberField
          label="Waypoint sequence index"
          value={event.waypoint_sequence_index ?? 0}
          onChange={(waypoint_sequence_index) => onChange({ ...event, waypoint_sequence_index })}
        />
      )}
      <TextField
        label="Offset (ISO8601 duration)"
        value={event.offset}
        onChange={(offset) => onChange({ ...event, offset })}
      />
    </>
  );
}
