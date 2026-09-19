import type { ReactNode } from "react";
import { NavRail } from "./NavRail";
import { Subnav, type SubnavItem } from "./Subnav";
import { TopBar, type BreadcrumbItem } from "./TopBar";

export interface AppShellProps {
  breadcrumb: BreadcrumbItem[];
  actions?: ReactNode;
  /** Secondary collapsible nav panel (206px) — page title + subsection list. Omit for pages with nothing to list. */
  subnav?: { pageTitle: string; items: SubnavItem[]; footer?: string };
  /** Set false for pages that manage their own scrolling/height (map-heavy pages); default true padded-scroll. */
  scroll?: boolean;
  children: ReactNode;
}

/**
 * The chrome every page shares: a persistent left icon nav rail, an
 * optional collapsible secondary sub-nav panel, and a top breadcrumb/
 * command bar. Everything else about a page's layout is up to the page.
 */
export function AppShell({ breadcrumb, actions, subnav, scroll = true, children }: AppShellProps) {
  return (
    <div style={{ display: "flex", height: "100%" }}>
      <NavRail />
      {subnav && (
        <Subnav pageTitle={subnav.pageTitle} items={subnav.items} footer={subnav.footer} />
      )}
      <div
        style={{
          flex: 1,
          minWidth: 0,
          display: "flex",
          flexDirection: "column",
          overflow: "hidden",
        }}
      >
        <TopBar breadcrumb={breadcrumb} actions={actions} />
        <div
          style={{
            flex: 1,
            minHeight: 0,
            overflowY: scroll ? "auto" : "hidden",
            background: "var(--bg)",
          }}
        >
          {children}
        </div>
      </div>
    </div>
  );
}
