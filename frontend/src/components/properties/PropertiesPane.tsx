import type { Dispatch } from "react";
import type { IQRecording, ScenarioContent, TimelineEvent } from "../../domain/types";
import type { EditorAction } from "../../state/editorReducer";
import type { Selection } from "../../state/selection";
import { MissionForm } from "./MissionForm";
import { ReceiverForm } from "./ReceiverForm";
import { TimelineEventForm } from "./TimelineEventForm";
import { ZoneForm } from "./ZoneForm";

export interface PropertiesPaneProps {
  content: ScenarioContent;
  selection: Selection;
  dispatch: Dispatch<EditorAction>;
  onClearSelection: () => void;
  catalogue: IQRecording[];
}

/** Dispatches by selected-object kind to the matching edit form. */
export function PropertiesPane({
  content,
  selection,
  dispatch,
  onClearSelection,
  catalogue,
}: PropertiesPaneProps) {
  if (selection === null) {
    return (
      <div style={{ padding: 16, color: "#4c5c5e", fontSize: 13 }}>
        Select a zone, mission, waypoint, receiver or RF link on the map to edit it.
      </div>
    );
  }

  switch (selection.kind) {
    case "zone": {
      const zone = content.zones.find((z) => z.id === selection.id);
      if (!zone) return <NotFound />;
      return (
        <ZoneForm
          zone={zone}
          onChange={(updated) =>
            dispatch({
              type: "setZones",
              zones: content.zones.map((z) => (z.id === updated.id ? updated : z)),
            })
          }
          onDelete={() => {
            dispatch({ type: "setZones", zones: content.zones.filter((z) => z.id !== zone.id) });
            onClearSelection();
          }}
        />
      );
    }
    case "mission":
    case "waypoint":
    case "rfLink": {
      const missionId = selection.kind === "mission" ? selection.id : selection.missionId;
      const mission = content.missions.find((m) => m.id === missionId);
      if (!mission) return <NotFound />;
      return (
        <MissionForm
          mission={mission}
          onChange={(updated) =>
            dispatch({
              type: "setMissions",
              missions: content.missions.map((m) => (m.id === updated.id ? updated : m)),
            })
          }
          onDelete={() => {
            dispatch({
              type: "setMissions",
              missions: content.missions.filter((m) => m.id !== mission.id),
            });
            onClearSelection();
          }}
          catalogue={catalogue}
        />
      );
    }
    case "receiver": {
      const receiver = content.receivers.find((r) => r.id === selection.id);
      if (!receiver) return <NotFound />;
      return (
        <ReceiverForm
          receiver={receiver}
          onChange={(updated) =>
            dispatch({
              type: "setReceivers",
              receivers: content.receivers.map((r) => (r.id === updated.id ? updated : r)),
            })
          }
          onDelete={() => {
            dispatch({
              type: "setReceivers",
              receivers: content.receivers.filter((r) => r.id !== receiver.id),
            });
            onClearSelection();
          }}
        />
      );
    }
    case "timelineEvent": {
      const event = content.timeline_events.find((e) => e.id === selection.id);
      if (!event) return <NotFound />;
      return (
        <TimelineEventForm
          event={event}
          missions={content.missions}
          onChange={(updated: TimelineEvent) =>
            dispatch({
              type: "setTimelineEvents",
              events: content.timeline_events.map((e) => (e.id === updated.id ? updated : e)),
            })
          }
          onDelete={() => {
            dispatch({
              type: "setTimelineEvents",
              events: content.timeline_events.filter((e) => e.id !== event.id),
            });
            onClearSelection();
          }}
        />
      );
    }
  }
}

function NotFound() {
  return <div style={{ padding: 16 }}>Not found.</div>;
}
