import type { ScenarioContent, ValidationFinding } from "../../domain/types";
import type { Selection } from "../../state/selection";
import { Card } from "../shell/Card";
import { ValidationFindingsPanel } from "./ValidationFindingsPanel";

export interface PublishBlockedDialogProps {
  findings: ValidationFinding[];
  content: ScenarioContent;
  onSelectPath: (selection: Selection) => void;
  onClose: () => void;
}

/** Shown when publish returns 422 — blocking findings prevented it. */
export function PublishBlockedDialog({
  findings,
  content,
  onSelectPath,
  onClose,
}: PublishBlockedDialogProps) {
  return (
    <div
      role="dialog"
      aria-label="Publish blocked"
      style={{
        position: "fixed",
        inset: 0,
        background: "var(--surface-overlay)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 100,
      }}
    >
      <div style={{ maxWidth: 480, width: "90%" }}>
        <Card title="Publish blocked">
          <p style={{ fontSize: 13, marginTop: 0, color: "var(--text-secondary)" }}>
            This draft has blocking validation findings. Fix them, then validate again before
            publishing.
          </p>
          <ValidationFindingsPanel
            findings={findings}
            content={content}
            onSelectPath={(selection) => {
              onSelectPath(selection);
              onClose();
            }}
          />
          <button type="button" onClick={onClose} style={{ marginTop: 12 }}>
            Close
          </button>
        </Card>
      </div>
    </div>
  );
}
