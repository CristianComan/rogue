export type BadgeTone = "success" | "warning" | "danger" | "info" | "neutral";

const TONE_VARS: Record<BadgeTone, { fg: string; bg: string }> = {
  success: { fg: "var(--status-success)", bg: "var(--status-success-bg)" },
  warning: { fg: "var(--status-warning)", bg: "var(--status-warning-bg)" },
  danger: { fg: "var(--status-danger)", bg: "var(--status-danger-bg)" },
  info: { fg: "var(--status-info)", bg: "var(--status-info-bg)" },
  neutral: { fg: "var(--status-neutral)", bg: "var(--status-neutral-bg)" },
};

/** A small status pill, matching Azure Portal's state-badge convention. */
export function Badge({ tone, children }: { tone: BadgeTone; children: string }) {
  const { fg, bg } = TONE_VARS[tone];
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 4,
        padding: "2px 8px",
        borderRadius: 2,
        fontSize: 11,
        fontWeight: 600,
        letterSpacing: "0.02em",
        textTransform: "uppercase",
        color: fg,
        background: bg,
        whiteSpace: "nowrap",
      }}
    >
      <span aria-hidden style={{ width: 6, height: 6, borderRadius: "50%", background: fg }} />
      {children}
    </span>
  );
}
