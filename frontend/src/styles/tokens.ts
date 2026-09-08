/**
 * Thin re-export of index.css's design tokens for use in inline style
 * objects (React style props can't reference CSS custom properties by
 * name directly the way a stylesheet rule can, but `var(--x)` as a string
 * value works fine) — one source of truth in the CSS file, this module
 * just names them for TypeScript call sites.
 */

import type { CSSProperties } from "react";

export const colors = {
  border: "var(--border-default)",
  borderLight: "var(--border-subtle)",
  textMuted: "var(--text-secondary)",
  panelHeading: "var(--text-secondary)",
  selectedBg: "var(--surface-selected)",
  monoBg: "var(--surface-sunken)",
  severity: {
    info: "var(--status-info)",
    warning: "var(--status-warning)",
    blocking: "var(--status-danger)",
    critical: "var(--status-danger)",
  },
  status: {
    online: "var(--status-success)",
    stale: "var(--status-warning)",
    offline: "var(--status-neutral)",
  },
} as const;

export const monoFontStack = "var(--font-mono)";

export const sectionHeadingStyle: CSSProperties = {
  fontSize: 11,
  fontWeight: 700,
  letterSpacing: "0.06em",
  textTransform: "uppercase",
  color: colors.panelHeading,
};

export function severityColor(severity: "warning" | "blocking" | "info" | "critical"): string {
  return colors.severity[severity];
}
