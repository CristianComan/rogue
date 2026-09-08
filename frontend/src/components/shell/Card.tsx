import type { CSSProperties, ReactNode } from "react";

export function Card({
  title,
  actions,
  header,
  children,
  style,
  bodyStyle,
  noPadding,
}: {
  title?: ReactNode;
  actions?: ReactNode;
  /** Full custom header row, overriding title/actions — for panels (e.g. with their own tabs) that need more than a label + right-aligned actions. */
  header?: ReactNode;
  children: ReactNode;
  style?: CSSProperties;
  bodyStyle?: CSSProperties;
  noPadding?: boolean;
}) {
  const headerContent =
    header ??
    (title || actions ? (
      <>
        {title && (
          <div
            style={{
              fontSize: 11,
              fontWeight: 600,
              letterSpacing: "0.06em",
              textTransform: "uppercase",
              color: "var(--text-secondary)",
            }}
          >
            {title}
          </div>
        )}
        {actions && <div style={{ marginLeft: "auto", display: "flex", gap: 6 }}>{actions}</div>}
      </>
    ) : null);

  return (
    <section
      style={{
        background: "var(--surface-card)",
        border: "1px solid var(--border-default)",
        borderRadius: "var(--radius)",
        display: "flex",
        flexDirection: "column",
        minHeight: 0,
        ...style,
      }}
    >
      {headerContent && (
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 8,
            padding: "10px 14px",
            borderBottom: "1px solid var(--border-subtle)",
            flex: "0 0 auto",
          }}
        >
          {headerContent}
        </div>
      )}
      <div style={{ flex: 1, minHeight: 0, padding: noPadding ? 0 : 14, ...bodyStyle }}>
        {children}
      </div>
    </section>
  );
}
