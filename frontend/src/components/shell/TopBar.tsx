import type { ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { useUiPreferences } from "../../state/uiPreferencesContext";

export interface BreadcrumbItem {
  label: string;
  to?: string;
}

export function TopBar({
  breadcrumb,
  actions,
}: {
  breadcrumb: BreadcrumbItem[];
  actions?: ReactNode;
}) {
  const navigate = useNavigate();
  const { toggleNav } = useUiPreferences();

  return (
    <header
      style={{
        height: 44,
        flex: "0 0 44px",
        display: "flex",
        alignItems: "center",
        gap: 10,
        padding: "0 12px",
        background: "var(--surface)",
        borderBottom: "1px solid var(--line)",
      }}
    >
      <button
        type="button"
        onClick={toggleNav}
        title="Toggle sub-navigation"
        style={{
          width: 26,
          height: 26,
          display: "grid",
          placeItems: "center",
          background: "transparent",
          border: "1px solid var(--line)",
          borderRadius: 2,
          color: "var(--ink-2)",
          font: "500 11px/1 var(--mono)",
          padding: 0,
        }}
      >
        ≡
      </button>
      <nav
        aria-label="Breadcrumb"
        style={{
          display: "flex",
          alignItems: "center",
          gap: 6,
          minWidth: 0,
          overflow: "hidden",
          flex: "0 1 auto",
          fontSize: 12.5,
        }}
      >
        {breadcrumb.map((item, index) => {
          const isLast = index === breadcrumb.length - 1;
          return (
            <span
              key={`${item.label}-${index}`}
              style={{ display: "flex", alignItems: "center", gap: 6, minWidth: 0, overflow: "hidden" }}
            >
              {index > 0 && (
                <span aria-hidden style={{ color: "var(--line-2)", flex: "0 0 auto" }}>
                  /
                </span>
              )}
              {item.to && !isLast ? (
                <button
                  type="button"
                  onClick={() => navigate(item.to!)}
                  style={{
                    background: "none",
                    border: "none",
                    padding: 0,
                    color: "var(--ink-3)",
                    fontSize: 12.5,
                    fontWeight: 400,
                    cursor: "pointer",
                  }}
                >
                  {item.label}
                </button>
              ) : (
                <span
                  style={{
                    fontWeight: isLast ? 600 : 400,
                    color: isLast ? "var(--ink)" : "var(--ink-3)",
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                    whiteSpace: "nowrap",
                  }}
                >
                  {item.label}
                </span>
              )}
            </span>
          );
        })}
      </nav>
      <div style={{ flex: "1 1 12px", minWidth: 12 }} />
      {actions && (
        <div style={{ display: "flex", alignItems: "center", gap: 6, flex: "0 0 auto" }}>
          {actions}
        </div>
      )}
    </header>
  );
}
