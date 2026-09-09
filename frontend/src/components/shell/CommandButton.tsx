/** The dot+label command-bar button from the design canvas's top bar (accent = the primary action, ghost = everything else). */
export function CommandButton({
  label,
  onClick,
  variant = "ghost",
  disabled,
}: {
  label: string;
  onClick?: () => void;
  variant?: "accent" | "ghost";
  disabled?: boolean;
}) {
  const accent = variant === "accent";
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      style={{
        display: "flex",
        alignItems: "center",
        gap: 6,
        height: 27,
        padding: "0 10px",
        background: accent ? "var(--accent)" : "var(--surface)",
        color: accent ? "#fff" : "var(--ink)",
        border: `1px solid ${accent ? "var(--accent)" : "var(--line-2)"}`,
        borderRadius: 2,
        fontSize: 12,
        fontWeight: 500,
        whiteSpace: "nowrap",
      }}
    >
      <span
        aria-hidden
        style={{
          width: 6,
          height: 6,
          borderRadius: accent ? "50%" : "1px",
          background: accent ? "rgba(255,255,255,.75)" : "var(--ink-3)",
        }}
      />
      {label}
    </button>
  );
}
