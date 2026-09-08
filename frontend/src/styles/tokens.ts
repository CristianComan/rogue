/**
 * Thin re-export of index.css's design tokens for use in inline style
 * objects (React style props can't reference CSS custom properties by
 * name directly the way a stylesheet rule can, but `var(--x)` as a string
 * value works fine) — one source of truth in the CSS file, this module
 * just names them for TypeScript call sites.
 *
 * `Tone` mirrors the ROGUE Console design canvas's five-tone system
 * (ok/warn/bad/info/mute), each with fg/bg/bd CSS variables — the same
 * naming Badge.tsx and every status pill/table cell bind against.
 */

import type { CSSProperties } from "react";

export type Tone = "ok" | "warn" | "bad" | "info" | "mute";

export function toneVars(tone: Tone): { fg: string; bg: string; bd: string } {
  return { fg: `var(--${tone}-fg)`, bg: `var(--${tone}-bg)`, bd: `var(--${tone}-bd)` };
}

export const colors = {
  border: "var(--line-2)",
  borderLight: "var(--line)",
  textMuted: "var(--ink-2)",
  panelHeading: "var(--ink-3)",
  selectedBg: "var(--accent-soft)",
  monoBg: "var(--surface-3)",
  severity: {
    info: "var(--info-fg)",
    warning: "var(--warn-fg)",
    blocking: "var(--bad-fg)",
    critical: "var(--bad-fg)",
  },
  status: {
    online: "var(--ok-fg)",
    stale: "var(--warn-fg)",
    offline: "var(--mute-fg)",
  },
} as const;

export const monoFontStack = "var(--mono)";

export const sectionHeadingStyle: CSSProperties = {
  font: "600 11px/1.2 var(--mono)",
  letterSpacing: "0.09em",
  textTransform: "uppercase",
  color: "var(--ink-3)",
};

export function severityColor(severity: "warning" | "blocking" | "info" | "critical"): string {
  return colors.severity[severity];
}
