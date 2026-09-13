import type { TimelineEvent } from "../../domain/types";
import type { Selection } from "../../state/selection";

export interface TimelineEventsListEditorProps {
  events: TimelineEvent[];
  selection: Selection;
  onSelect: (selection: Selection) => void;
}

function describe(event: TimelineEvent): string {
  const label = event.label || "(unlabeled)";
  switch (event.kind) {
    case "absolute":
      return `${label} · absolute @ ${event.scenario_time_offset}`;
    case "mission_relative":
      return `${label} · mission-relative (${event.anchor})`;
    case "manual_gated":
      return `${label} · manual gate`;
    case "external":
      return `${label} · external (${event.source})`;
    case "safety":
      return `${label} · safety (${event.safety_kind})`;
  }
}

/**
 * An always-visible list of the scenario's timeline events. Unlike zones/
 * missions/receivers, a timeline event has no geometry at all — there is no
 * map feature to click, so without this list an event becomes permanently
 * unselectable (and therefore uneditable/undeletable) the moment focus
 * moves away from it after creation. Not an inline editor: events already
 * have real create (toolbar)/edit (TimelineEventForm)/delete
 * (TimelineEventForm) — this only adds the missing "select an existing one"
 * affordance.
 */
export function TimelineEventsListEditor({
  events,
  selection,
  onSelect,
}: TimelineEventsListEditorProps) {
  return (
    <div
      data-testid="timeline-events-panel"
      style={{ display: "flex", flexDirection: "column", gap: 4, padding: 12 }}
    >
      <strong style={{ fontSize: 12 }}>Timeline events</strong>
      {events.length === 0 && (
        <span style={{ fontSize: 12, color: "#4c5c5e" }}>No timeline events in this scenario.</span>
      )}
      {events.map((event) => {
        const isSelected = selection?.kind === "timelineEvent" && selection.id === event.id;
        return (
          <button
            key={event.id}
            type="button"
            data-testid={`timeline-events-panel-row-${event.id}`}
            onClick={() => onSelect({ kind: "timelineEvent", id: event.id })}
            style={{
              textAlign: "left",
              fontSize: 12,
              padding: "4px 6px",
              background: isSelected ? "#e4ebe8" : "transparent",
              border: "1px solid #ccc",
              cursor: "pointer",
            }}
          >
            {describe(event)}
          </button>
        );
      })}
    </div>
  );
}
