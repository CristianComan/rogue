import { describe, expect, it } from "vitest";
import { editorReducer, initialEditorState, type EditorState } from "./editorReducer";
import type { ScenarioDraft, Zone } from "../domain/types";

const ZONE: Zone = {
  id: "z1",
  zone_type: "operational_area",
  polygon: {
    type: "Polygon",
    coordinates: [
      [
        [0, 0],
        [1, 0],
        [1, 1],
        [0, 0],
      ],
    ],
  },
  label: null,
  notes: null,
};

const DRAFT: ScenarioDraft = {
  id: "d1",
  scenario_id: "s1",
  base_version_id: null,
  revision: 2,
  author: "alice",
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
  zones: [ZONE],
  missions: [],
  receivers: [],
  timeline_events: [],
  recordings: [],
};

describe("editorReducer", () => {
  it("loadDraft resets content/revision/author and clears dirty", () => {
    const state = editorReducer(initialEditorState, { type: "loadDraft", draft: DRAFT });

    expect(state.draftId).toBe("d1");
    expect(state.scenarioId).toBe("s1");
    expect(state.revision).toBe(2);
    expect(state.author).toBe("alice");
    expect(state.content.zones).toEqual([ZONE]);
    expect(state.dirty).toBe(false);
  });

  it("setZones replaces zones and marks dirty, without mutating the input state", () => {
    const loaded = editorReducer(initialEditorState, { type: "loadDraft", draft: DRAFT });
    const next = editorReducer(loaded, { type: "setZones", zones: [] });

    expect(next.content.zones).toEqual([]);
    expect(next.dirty).toBe(true);
    expect(loaded.content.zones).toEqual([ZONE]); // original untouched
  });

  it("setMissions marks dirty", () => {
    expect(editorReducer(initialEditorState, { type: "setMissions", missions: [] }).dirty).toBe(
      true,
    );
  });

  it("setReceivers marks dirty", () => {
    expect(editorReducer(initialEditorState, { type: "setReceivers", receivers: [] }).dirty).toBe(
      true,
    );
  });

  it("setTimelineEvents marks dirty", () => {
    expect(editorReducer(initialEditorState, { type: "setTimelineEvents", events: [] }).dirty).toBe(
      true,
    );
  });

  it("setRecordings marks dirty", () => {
    expect(editorReducer(initialEditorState, { type: "setRecordings", recordings: [] }).dirty).toBe(
      true,
    );
  });

  it("savedSuccessfully updates revision and clears dirty", () => {
    const dirty: EditorState = { ...initialEditorState, dirty: true, revision: 1 };
    const next = editorReducer(dirty, { type: "savedSuccessfully", revision: 5 });

    expect(next.revision).toBe(5);
    expect(next.dirty).toBe(false);
  });
});
