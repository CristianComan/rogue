import { toneVars, type Tone } from "../../styles/tokens";

/** @deprecated tone names — kept so existing call sites (BadgeTone) keep compiling; prefer Tone ("ok"|"warn"|"bad"|"info"|"mute") directly. */
export type BadgeTone = "success" | "warning" | "danger" | "info" | "neutral";

const LEGACY_TONE_MAP: Record<BadgeTone, Tone> = {
  success: "ok",
  warning: "warn",
  danger: "bad",
  info: "info",
  neutral: "mute",
};

/** A small rounded status pill with a dot, matching the ROGUE Console canvas's tone system. */
export function Badge({ tone, children }: { tone: BadgeTone | Tone; children: string }) {
  const resolved: Tone = tone in LEGACY_TONE_MAP ? LEGACY_TONE_MAP[tone as BadgeTone] : (tone as Tone);
  const { fg, bg, bd } = toneVars(resolved);
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 5,
        padding: "1px 7px",
        borderRadius: 10,
        fontSize: 11.5,
        fontWeight: 500,
        color: fg,
        background: bg,
        border: `1px solid ${bd}`,
        whiteSpace: "nowrap",
      }}
    >
      <span aria-hidden style={{ width: 5, height: 5, borderRadius: "50%", background: fg }} />
      {children}
    </span>
  );
}
