/**
 * Shared visual constants for the badges/tables introduced across the
 * Spatial/Signal/Replay/Console views — kept as plain values (not a CSS
 * framework) to match this codebase's existing inline-style convention.
 */

import type { CSSProperties } from "react";

export const colors = {
  border: "#ccc",
  borderLight: "#eee",
  textMuted: "#4c5c5e",
  panelHeading: "#2f3a3c",
  selectedBg: "#e4ebe8",
  monoBg: "#f5f7f6",
  severity: {
    info: "#3568b0",
    warning: "#b8790e",
    blocking: "#b3261e",
    critical: "#b3261e",
  },
  status: {
    online: "#1e8e3e",
    stale: "#b8790e",
    offline: "#8a8f8c",
  },
} as const;

export const monoFontStack = "ui-monospace, SFMono-Regular, 'Cascadia Code', Consolas, monospace";

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
