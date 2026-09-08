import type { ReactNode } from "react";
import { useLocation, useNavigate } from "react-router-dom";

interface NavItem {
  label: string;
  to: string;
  icon: ReactNode;
  isActive: (pathname: string) => boolean;
}

function HomeIcon() {
  return (
    <svg
      width="20"
      height="20"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
    >
      <path d="M4 11.5 12 4l8 7.5" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M6 10v9h12v-9" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function AntennaIcon() {
  return (
    <svg
      width="20"
      height="20"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
    >
      <path d="M12 3v11" strokeLinecap="round" />
      <path d="M12 14l-3 7h6l-3-7Z" strokeLinejoin="round" />
      <path d="M7 6a7 7 0 0 0 0 5" strokeLinecap="round" />
      <path d="M17 6a7 7 0 0 1 0 5" strokeLinecap="round" />
      <path d="M4 3a11 11 0 0 0 0 8" strokeLinecap="round" />
      <path d="M20 3a11 11 0 0 1 0 8" strokeLinecap="round" />
    </svg>
  );
}

const ITEMS: NavItem[] = [
  {
    label: "Scenario Library",
    to: "/",
    icon: <HomeIcon />,
    isActive: (p) => p === "/",
  },
  {
    label: "SDR Console",
    to: "/agents",
    icon: <AntennaIcon />,
    isActive: (p) => p.startsWith("/agents"),
  },
];

/** Persistent left icon nav rail — the one piece of chrome every page shares. */
export function NavRail() {
  const navigate = useNavigate();
  const location = useLocation();

  return (
    <nav
      aria-label="Primary"
      style={{
        width: "var(--nav-width)",
        flex: "0 0 auto",
        background: "var(--surface-nav)",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        paddingTop: 12,
        gap: 4,
      }}
    >
      <div
        aria-hidden
        title="ROGUE"
        style={{
          width: 28,
          height: 28,
          borderRadius: 6,
          background: "var(--surface-nav-active)",
          color: "var(--text-on-accent)",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          fontSize: 12,
          fontWeight: 700,
          marginBottom: 16,
        }}
      >
        R
      </div>
      {ITEMS.map((item) => {
        const active = item.isActive(location.pathname);
        return (
          <button
            key={item.to}
            type="button"
            title={item.label}
            aria-label={item.label}
            aria-current={active ? "page" : undefined}
            onClick={() => navigate(item.to)}
            style={{
              width: 36,
              height: 36,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              background: active ? "var(--surface-nav-active)" : "transparent",
              border: "none",
              borderRadius: 6,
              color: active ? "var(--text-on-accent)" : "var(--text-on-nav)",
              cursor: "pointer",
            }}
            onMouseEnter={(e) => {
              if (!active) e.currentTarget.style.background = "var(--surface-nav-hover)";
            }}
            onMouseLeave={(e) => {
              if (!active) e.currentTarget.style.background = "transparent";
            }}
          >
            {item.icon}
          </button>
        );
      })}
    </nav>
  );
}
