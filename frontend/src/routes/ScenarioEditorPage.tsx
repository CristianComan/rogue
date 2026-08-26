import { useEffect, useReducer, useState } from "react";
import type { Dispatch } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { ConflictError, PublishBlockedError } from "../api/client";
import {
  createDraft,
  getVersion,
  listVersions,
  publishDraft,
  updateDraft,
  validateDraft,
} from "../api/scenarios";
import { EditorLayout } from "../components/editor/EditorLayout";
import { PublishBlockedDialog } from "../components/editor/PublishBlockedDialog";
import { ScenarioToolbar } from "../components/editor/ScenarioToolbar";
import { ValidationFindingsPanel } from "../components/editor/ValidationFindingsPanel";
import { TimelinePane } from "../components/timeline/TimelinePane";
import { scenarioDurationSeconds } from "../domain/missionEvaluator";
import type { ValidationFinding } from "../domain/types";
import {
  editorReducer,
  initialEditorState,
  type EditorAction,
  type EditorState,
} from "../state/editorReducer";
import { ScenarioTimeProvider, useScenarioTime } from "../state/scenarioTimeContext";
import { SelectionProvider, useSelection } from "../state/selectionContext";

/**
 * Phase 7 checkpoint: the full library -> editor -> validate -> publish
 * loop. Scenario id comes from the route (react-router-dom), not a
 * dropdown — see routes/ScenarioLibraryPage.tsx for how you get here.
 */
export function ScenarioEditorPage() {
  const { scenarioId } = useParams<{ scenarioId: string }>();
  const navigate = useNavigate();
  const [state, dispatch] = useReducer(editorReducer, initialEditorState);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [validating, setValidating] = useState(false);
  const [validationFindings, setValidationFindings] = useState<ValidationFinding[] | null>(null);
  const [publishing, setPublishing] = useState(false);
  const [publishedVersionNumber, setPublishedVersionNumber] = useState<number | null>(null);
  const [blockedFindings, setBlockedFindings] = useState<ValidationFinding[] | null>(null);

  useEffect(() => {
    if (!scenarioId) return;
    setLoadError(null);
    // React 19 StrictMode double-invokes this effect in dev (mount, then
    // mount again with no cleanup in between), which would otherwise create
    // two drafts and leave the UI non-deterministically bound to whichever
    // one resolved last. The `cancelled` flag makes the outcome
    // deterministic: state only ever binds to the most recently mounted
    // effect's draft, per React's own documented pattern for this case.
    let cancelled = false;

    async function loadOrCreateDraft() {
      const versions = await listVersions(scenarioId!);
      const latest =
        versions.length > 0
          ? versions.reduce((a, b) => (a.version_number > b.version_number ? a : b))
          : null;
      const seed = latest ? await getVersion(scenarioId!, latest.version_number) : null;

      const draft = await createDraft(scenarioId!, {
        author: "dev",
        base_version_id: seed?.id ?? null,
        zones: seed?.zones ?? [],
        missions: seed?.missions ?? [],
        receivers: seed?.receivers ?? [],
        timeline_events: seed?.timeline_events ?? [],
        recordings: seed?.recordings ?? [],
      });
      if (!cancelled) dispatch({ type: "loadDraft", draft });
    }

    loadOrCreateDraft().catch((e) => {
      if (!cancelled) setLoadError(String(e));
    });
    return () => {
      cancelled = true;
    };
  }, [scenarioId]);

  async function handleSave() {
    if (!state.scenarioId || !state.draftId) return;
    setSaving(true);
    setSaveError(null);
    try {
      const saved = await updateDraft(state.scenarioId, state.draftId, {
        author: state.author,
        expected_revision: state.revision,
        ...state.content,
      });
      dispatch({ type: "savedSuccessfully", revision: saved.revision });
    } catch (err) {
      if (err instanceof ConflictError) {
        setSaveError(
          "This draft was updated elsewhere since it was loaded (revision mismatch). " +
            "Reload the page to get the latest version before saving again.",
        );
      } else {
        setSaveError(err instanceof Error ? err.message : String(err));
      }
    } finally {
      setSaving(false);
    }
  }

  async function handleValidate() {
    if (!state.scenarioId || !state.draftId) return;
    setValidating(true);
    try {
      setValidationFindings(await validateDraft(state.scenarioId, state.draftId));
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : String(err));
    } finally {
      setValidating(false);
    }
  }

  async function handlePublish() {
    if (!state.scenarioId || !state.draftId) return;
    setPublishing(true);
    setPublishedVersionNumber(null);
    try {
      const version = await publishDraft(state.scenarioId, state.draftId);
      setPublishedVersionNumber(version.version_number);
      setValidationFindings(version.validation_findings);
    } catch (err) {
      if (err instanceof PublishBlockedError) {
        setBlockedFindings(err.findings as ValidationFinding[]);
      } else {
        setSaveError(err instanceof Error ? err.message : String(err));
      }
    } finally {
      setPublishing(false);
    }
  }

  const maxSeconds = Math.max(1, scenarioDurationSeconds(state.content.missions));

  return (
    <SelectionProvider>
      <ScenarioTimeProvider maxSeconds={maxSeconds}>
        <div
          data-draft-id={state.draftId ?? undefined}
          style={{ display: "flex", flexDirection: "column", height: "100%" }}
        >
          <div style={{ padding: 8, borderBottom: "1px solid #ccc", display: "flex", gap: 12 }}>
            <button type="button" onClick={() => navigate("/")}>
              ← Library
            </button>
            <strong>ROGUE Scenario Editor</strong>
            {loadError && <span style={{ color: "crimson" }}>{loadError}</span>}
          </div>
          <div style={{ flex: 1, minHeight: 0 }}>
            <EditorBody
              state={state}
              dispatch={dispatch}
              maxSeconds={maxSeconds}
              onSave={handleSave}
              saving={saving}
              saveError={saveError}
              onValidate={handleValidate}
              validating={validating}
              validationFindings={validationFindings}
              onPublish={handlePublish}
              publishing={publishing}
              publishedVersionNumber={publishedVersionNumber}
            />
          </div>
          {blockedFindings && (
            <PublishBlockedDialogHost
              findings={blockedFindings}
              content={state.content}
              onClose={() => setBlockedFindings(null)}
            />
          )}
        </div>
      </ScenarioTimeProvider>
    </SelectionProvider>
  );
}

function PublishBlockedDialogHost({
  findings,
  content,
  onClose,
}: {
  findings: ValidationFinding[];
  content: EditorState["content"];
  onClose: () => void;
}) {
  const { select } = useSelection();
  return (
    <PublishBlockedDialog
      findings={findings}
      content={content}
      onSelectPath={select}
      onClose={onClose}
    />
  );
}

function EditorBody({
  state,
  dispatch,
  maxSeconds,
  onSave,
  saving,
  saveError,
  onValidate,
  validating,
  validationFindings,
  onPublish,
  publishing,
  publishedVersionNumber,
}: {
  state: EditorState;
  dispatch: Dispatch<EditorAction>;
  maxSeconds: number;
  onSave: () => void;
  saving: boolean;
  saveError: string | null;
  onValidate: () => void;
  validating: boolean;
  validationFindings: ValidationFinding[] | null;
  onPublish: () => void;
  publishing: boolean;
  publishedVersionNumber: number | null;
}) {
  const { scenarioTimeSeconds } = useScenarioTime();
  const { select } = useSelection();

  return (
    <EditorLayout
      content={state.content}
      scenarioTimeSeconds={scenarioTimeSeconds}
      dispatch={dispatch}
      toolbar={
        state.draftId && (
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            <ScenarioToolbar
              state={state}
              dispatch={dispatch}
              onSave={onSave}
              saving={saving}
              saveError={saveError}
              onValidate={onValidate}
              validating={validating}
              onPublish={onPublish}
              publishing={publishing}
              publishedVersionNumber={publishedVersionNumber}
            />
            {validationFindings && (
              <ValidationFindingsPanel
                findings={validationFindings}
                content={state.content}
                onSelectPath={select}
              />
            )}
          </div>
        )
      }
      timeline={<TimelinePane missions={state.content.missions} maxSeconds={maxSeconds} />}
    />
  );
}
