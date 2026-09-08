import type { ReactNode } from "react";
import { useNavigate } from "react-router-dom";

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

  return (
    <header
      style={{
        flex: "0 0 auto",
        display: "flex",
        alignItems: "center",
        gap: 8,
        padding: "10px 20px",
        background: "var(--surface-card)",
        borderBottom: "1px solid var(--border-default)",
        minHeight: 20,
      }}
    >
      <nav
        aria-label="Breadcrumb"
        style={{ display: "flex", alignItems: "center", gap: 6, minWidth: 0 }}
      >
        {breadcrumb.map((item, index) => {
          const isLast = index === breadcrumb.length - 1;
          return (
            <span
              key={`${item.label}-${index}`}
              style={{ display: "flex", alignItems: "center", gap: 6 }}
            >
              {index > 0 && (
                <span aria-hidden style={{ color: "var(--text-tertiary)", fontSize: 12 }}>
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
                    color: "var(--text-secondary)",
                    fontSize: 13,
                    cursor: "pointer",
                  }}
                >
                  {item.label}
                </button>
              ) : (
                <span
                  style={{
                    fontSize: 14,
                    fontWeight: isLast ? 600 : 400,
                    color: isLast ? "var(--text-primary)" : "var(--text-secondary)",
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
      {actions && (
        <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 8 }}>
          {actions}
        </div>
      )}
    </header>
  );
}
