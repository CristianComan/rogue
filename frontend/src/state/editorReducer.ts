import type {
  DroneMission,
  Receiver,
  ScenarioContent,
  ScenarioDraft,
  TimelineEvent,
  Zone,
} from "../domain/types";

export interface EditorState {
  draftId: string | null;
  scenarioId: string | null;
  content: ScenarioContent;
  revision: number;
  author: string;
  dirty: boolean;
}

export type EditorAction =
  | { type: "loadDraft"; draft: ScenarioDraft }
  | { type: "setZones"; zones: Zone[] }
  | { type: "setMissions"; missions: DroneMission[] }
  | { type: "setReceivers"; receivers: Receiver[] }
  | { type: "setTimelineEvents"; events: TimelineEvent[] }
  | { type: "savedSuccessfully"; revision: number };

export const initialEditorState: EditorState = {
  draftId: null,
  scenarioId: null,
  content: { zones: [], missions: [], receivers: [], timeline_events: [] },
  revision: 0,
  author: "",
  dirty: false,
};

export function editorReducer(state: EditorState, action: EditorAction): EditorState {
  switch (action.type) {
    case "loadDraft":
      return {
        draftId: action.draft.id,
        scenarioId: action.draft.scenario_id,
        content: {
          zones: action.draft.zones,
          missions: action.draft.missions,
          receivers: action.draft.receivers,
          timeline_events: action.draft.timeline_events,
        },
        revision: action.draft.revision,
        author: action.draft.author,
        dirty: false,
      };
    case "setZones":
      return { ...state, content: { ...state.content, zones: action.zones }, dirty: true };
    case "setMissions":
      return { ...state, content: { ...state.content, missions: action.missions }, dirty: true };
    case "setReceivers":
      return { ...state, content: { ...state.content, receivers: action.receivers }, dirty: true };
    case "setTimelineEvents":
      return {
        ...state,
        content: { ...state.content, timeline_events: action.events },
        dirty: true,
      };
    case "savedSuccessfully":
      return { ...state, revision: action.revision, dirty: false };
  }
}
