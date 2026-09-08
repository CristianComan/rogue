import type { ReactNode } from "react";
import { NavRail } from "./NavRail";
import { TopBar, type BreadcrumbItem } from "./TopBar";

export interface AppShellProps {
  breadcrumb: BreadcrumbItem[];
  actions?: ReactNode;
  /** Set false for pages that manage their own scrolling/height (map-heavy pages); default true padded-scroll. */
  scroll?: boolean;
  children: ReactNode;
}

/**
 * The one piece of chrome every page shares: a persistent left icon nav
 * rail and a top breadcrumb/action bar. Everything else about a page's
 * layout is up to the page itself.
 */
export function AppShell({ breadcrumb, actions, scroll = true, children }: AppShellProps) {
  return (
    <div style={{ display: "flex", height: "100%" }}>
      <NavRail />
      <div style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column" }}>
        <TopBar breadcrumb={breadcrumb} actions={actions} />
        <div
          style={{
            flex: 1,
            minHeight: 0,
            overflowY: scroll ? "auto" : "hidden",
            background: "var(--surface-canvas)",
          }}
        >
          {children}
        </div>
      </div>
    </div>
  );
}
