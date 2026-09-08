import { useUiPreferences } from "../../state/uiPreferencesContext";

export interface SubnavItem {
  label: string;
  count?: string | number;
  active?: boolean;
  onClick?: () => void;
}

/**
 * The collapsible secondary nav panel (206px) — page title plus a list of
 * subsections with counts. Toggled via TopBar's hamburger button
 * (navOpen lives in uiPreferencesContext so it survives navigation).
 */
export function Subnav({
  pageTitle,
  items,
  footer,
}: {
  pageTitle: string;
  items: SubnavItem[];
  footer?: string;
}) {
  const { navOpen } = useUiPreferences();
  if (!navOpen) return null;

  return (
    <div
      style={{
        width: "var(--subnav-width)",
        flex: "0 0 auto",
        background: "var(--surface-2)",
        borderRight: "1px solid var(--line)",
        display: "flex",
        flexDirection: "column",
        overflow: "hidden",
      }}
    >
      <div style={{ padding: "12px 14px 10px", borderBottom: "1px solid var(--line)" }}>
        <div
          style={{
            font: "600 11px/1.2 var(--mono)",
            letterSpacing: "0.1em",
            textTransform: "uppercase",
            color: "var(--ink-3)",
          }}
        >
          ROGUE
        </div>
        <div style={{ fontSize: 14, fontWeight: 600, marginTop: 3 }}>{pageTitle}</div>
      </div>
      <div style={{ padding: "8px 0", overflow: "auto", flex: 1 }}>
        {items.map((item, i) => (
          <button
            key={`${item.label}-${i}`}
            type="button"
            onClick={item.onClick}
            style={{
              width: "100%",
              textAlign: "left",
              display: "flex",
              alignItems: "center",
              gap: 8,
              padding: "6px 14px 6px 12px",
              background: item.active ? "var(--surface-3)" : "transparent",
              border: "none",
              borderLeft: `2px solid ${item.active ? "var(--accent)" : "transparent"}`,
              borderRadius: 0,
              color: "var(--ink)",
              fontSize: 12.5,
              fontWeight: item.active ? 600 : 400,
              cursor: item.onClick ? "pointer" : "default",
            }}
          >
            <span style={{ flex: 1 }}>{item.label}</span>
            {item.count !== undefined && (
              <span style={{ font: "500 10px/1 var(--mono)", color: "var(--ink-3)" }}>
                {item.count}
              </span>
            )}
          </button>
        ))}
      </div>
      {footer && (
        <div
          style={{
            padding: "10px 14px",
            borderTop: "1px solid var(--line)",
            font: "400 10.5px/1.5 var(--mono)",
            color: "var(--ink-3)",
          }}
        >
          {footer}
        </div>
      )}
    </div>
  );
}
