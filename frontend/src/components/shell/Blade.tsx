import type { ReactNode } from "react";

/**
 * The generic entity-inspection "blade" — a right-docked slide-over used
 * throughout the ROGUE Console design canvas for detail views that don't
 * warrant a full page (an agent's devices/channels, a channel tile's full
 * allocation detail, receiver-geometry/Doppler numbers). 520px by
 * convention; pass a wider `width` for a sub-view that needs more room
 * (e.g. a card grid), matching the canvas's own "520px (1080px for
 * sub-views)" note. Clicking the scrim (but not the panel itself) closes
 * it — the panel's own click handler stops propagation so an interactive
 * control inside it doesn't also dismiss the blade.
 */
export function Blade({
  kicker,
  title,
  sub,
  width = 520,
  onClose,
  headerExtra,
  children,
}: {
  kicker: string;
  title: string;
  sub?: string;
  width?: number;
  onClose: () => void;
  /** Extra header controls between the title block and the close button — e.g. the Doppler sub-view's independent scrub. */
  headerExtra?: ReactNode;
  children: ReactNode;
}) {
  return (
    <div
      data-testid="blade-scrim"
      onClick={onClose}
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(20,18,16,.28)",
        zIndex: 70,
        display: "flex",
        justifyContent: "flex-end",
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          width: `min(${width}px, 92vw)`,
          background: "var(--bg)",
          borderLeft: "1px solid var(--line-2)",
          boxShadow: "-8px 0 24px rgba(0,0,0,.18)",
          display: "flex",
          flexDirection: "column",
          overflow: "hidden",
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "flex-start",
            gap: 10,
            padding: "12px 16px",
            background: "var(--surface)",
            borderBottom: "1px solid var(--line)",
          }}
        >
          <div style={{ minWidth: 0, flex: 1 }}>
            <div
              style={{
                font: "600 10.5px/1.2 var(--mono)",
                letterSpacing: "0.09em",
                textTransform: "uppercase",
                color: "var(--ink-3)",
              }}
            >
              {kicker}
            </div>
            <div style={{ fontSize: 15, fontWeight: 600, marginTop: 2 }}>{title}</div>
            {sub && (
              <div
                style={{ font: "400 11px/1.5 var(--mono)", color: "var(--ink-3)", marginTop: 2 }}
              >
                {sub}
              </div>
            )}
          </div>
          {headerExtra}
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            style={{
              width: 27,
              height: 25,
              background: "var(--surface)",
              border: "1px solid var(--line-2)",
              borderRadius: 2,
              cursor: "pointer",
              color: "var(--ink-2)",
              fontSize: 13,
              flex: "0 0 auto",
            }}
          >
            ✕
          </button>
        </div>
        <div
          style={{
            flex: 1,
            overflow: "auto",
            padding: "13px 16px 20px",
            display: "flex",
            flexDirection: "column",
            gap: 12,
          }}
        >
          {children}
        </div>
      </div>
    </div>
  );
}

export interface BladeRow {
  k: string;
  v: ReactNode;
}

/** One key/value section card inside a Blade — the canvas's recurring "section of monospace rows" pattern. */
export function BladeSection({
  title,
  rows,
  note,
}: {
  title: string;
  rows: BladeRow[];
  note?: string;
}) {
  return (
    <div style={{ border: "1px solid var(--line)", borderRadius: 3, background: "var(--surface)" }}>
      <div
        style={{
          padding: "7px 11px",
          borderBottom: "1px solid var(--line)",
          background: "var(--surface-2)",
          font: "600 10.5px/1.2 var(--mono)",
          letterSpacing: "0.08em",
          textTransform: "uppercase",
          color: "var(--ink-3)",
        }}
      >
        {title}
      </div>
      <div style={{ padding: "9px 11px", display: "flex", flexDirection: "column", gap: 4 }}>
        {rows.map((row) => (
          <div
            key={row.k}
            style={{
              display: "grid",
              gridTemplateColumns: "auto 1fr",
              gap: 12,
              alignItems: "baseline",
              font: "400 11.5px/1.6 var(--mono)",
            }}
          >
            <span style={{ color: "var(--ink-3)" }}>{row.k}</span>
            <span style={{ color: "var(--ink)", textAlign: "right" }}>{row.v}</span>
          </div>
        ))}
        {note && (
          <div style={{ marginTop: 4, fontSize: 11.5, lineHeight: 1.5, color: "var(--ink-2)" }}>
            {note}
          </div>
        )}
      </div>
    </div>
  );
}
