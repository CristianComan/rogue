import type { Dispatch } from "react";
import { Link } from "react-router-dom";
import type { DroneMission, Receiver, TimelineEvent, Zone } from "../../domain/types";
import type { EditorAction, EditorState } from "../../state/editorReducer";
import { useSelection } from "../../state/selectionContext";

export interface ScenarioToolbarProps {
  state: EditorState;
  dispatch: Dispatch<EditorAction>;
  onSave: () => void;
  saving: boolean;
  saveError: string | null;
  onValidate: () => void;
  validating: boolean;
  onPublish: () => void;
  publishing: boolean;
  publishedVersionNumber: number | null;
}

function defaultZone(): Zone {
  return {
    id: crypto.randomUUID(),
    zone_type: "operational_area",
    polygon: {
      type: "Polygon",
      coordinates: [
        [
          [13.0, 52.0],
          [13.1, 52.0],
          [13.1, 52.1],
          [13.0, 52.1],
          [13.0, 52.0],
        ],
      ],
    },
    label: "New zone",
    notes: null,
  };
}

function defaultMission(): DroneMission {
  return {
    id: crypto.randomUUID(),
    name: "New mission",
    platform: {
      name: "Generic Quad",
      category: "multirotor",
      max_speed_mps: 15,
      max_climb_rate_mps: null,
      notes: null,
    },
    trajectory: {
      template: "waypoint_transit",
      default_speed_mps: 10,
      template_parameters: {},
      waypoints: [
        {
          sequence_index: 0,
          position: { type: "Point", coordinates: [13.4, 52.5] },
          altitude_m: 100,
          altitude_reference: "agl",
          speed_mps: null,
          heading_deg: null,
          hold_seconds: 0,
        },
        {
          sequence_index: 1,
          position: { type: "Point", coordinates: [13.41, 52.51] },
          altitude_m: 100,
          altitude_reference: "agl",
          speed_mps: null,
          heading_deg: null,
          hold_seconds: 0,
        },
      ],
    },
    start_policy: "at_scenario_start",
    start_time_offset: null,
    rf_links: [],
  };
}

function defaultReceiver(): Receiver {
  return {
    id: crypto.randomUUID(),
    name: "New receiver",
    receiver_type: "monitor",
    position: { type: "Point", coordinates: [13.42, 52.5] },
    array_group_id: null,
    element_index: null,
    element_local_offset_m: null,
  };
}

function defaultTimelineEvent(): TimelineEvent {
  return {
    id: crypto.randomUUID(),
    kind: "absolute",
    label: "New event",
    notes: null,
    scenario_time_offset: "PT0S",
  };
}

export function ScenarioToolbar({
  state,
  dispatch,
  onSave,
  saving,
  saveError,
  onValidate,
  validating,
  onPublish,
  publishing,
  publishedVersionNumber,
}: ScenarioToolbarProps) {
  const { select } = useSelection();

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
        <button
          type="button"
          onClick={() => {
            const zone = defaultZone();
            dispatch({ type: "setZones", zones: [...state.content.zones, zone] });
            select({ kind: "zone", id: zone.id });
          }}
        >
          + Zone
        </button>
        <button
          type="button"
          onClick={() => {
            const mission = defaultMission();
            dispatch({ type: "setMissions", missions: [...state.content.missions, mission] });
            select({ kind: "mission", id: mission.id });
          }}
        >
          + Mission
        </button>
        <button
          type="button"
          onClick={() => {
            const receiver = defaultReceiver();
            dispatch({ type: "setReceivers", receivers: [...state.content.receivers, receiver] });
            select({ kind: "receiver", id: receiver.id });
          }}
        >
          + Receiver
        </button>
        <button
          type="button"
          onClick={() => {
            const event = defaultTimelineEvent();
            dispatch({
              type: "setTimelineEvents",
              events: [...state.content.timeline_events, event],
            });
            select({ kind: "timelineEvent", id: event.id });
          }}
        >
          + Timeline event
        </button>
        <span style={{ flex: 1 }} />
        <span style={{ fontSize: 12, color: "#4c5c5e" }}>
          revision {state.revision}
          {state.dirty ? " · unsaved changes" : " · saved"}
        </span>
        <button type="button" onClick={onSave} disabled={!state.dirty || saving}>
          {saving ? "Saving…" : "Save"}
        </button>
        <button type="button" onClick={onValidate} disabled={validating}>
          {validating ? "Validating…" : "Validate"}
        </button>
        <button type="button" onClick={onPublish} disabled={publishing || state.dirty}>
          {publishing ? "Publishing…" : "Publish"}
        </button>
      </div>
      {saveError && <div style={{ color: "crimson", fontSize: 12 }}>{saveError}</div>}
      {state.dirty && (
        <div style={{ fontSize: 11, color: "#4c5c5e" }}>Save your changes before publishing.</div>
      )}
      {publishedVersionNumber !== null && state.scenarioId && (
        <div style={{ fontSize: 12, color: "#2c7a63" }}>
          Published version {publishedVersionNumber}.{" "}
          <Link to={`/scenarios/${state.scenarioId}/versions/${publishedVersionNumber}`}>
            View published version
          </Link>
        </div>
      )}
    </div>
  );
}
