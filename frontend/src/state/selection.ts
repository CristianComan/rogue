/**
 * The single source of truth for "what's selected," shared by the map, the
 * properties pane and the timeline — whichever pane changes it, the others
 * react to the same value. See EditorLayout (Phase 4) for how it's wired
 * into React Context.
 */
export type Selection =
  | { kind: "zone"; id: string }
  | { kind: "mission"; id: string }
  | { kind: "waypoint"; missionId: string; sequenceIndex: number }
  | { kind: "receiver"; id: string }
  | { kind: "rfLink"; missionId: string; linkId: string }
  | { kind: "timelineEvent"; id: string }
  | null;

export function selectionKey(selection: Selection): string | null {
  if (selection === null) return null;
  switch (selection.kind) {
    case "waypoint":
      return `waypoint:${selection.missionId}:${selection.sequenceIndex}`;
    case "rfLink":
      return `rfLink:${selection.missionId}:${selection.linkId}`;
    default:
      return `${selection.kind}:${selection.id}`;
  }
}
