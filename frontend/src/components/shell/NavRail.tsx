import { useLocation, useNavigate } from "react-router-dom";
import { useUiPreferences } from "../../state/uiPreferencesContext";

interface Glyph {
  x: number;
  y: number;
  w: number;
  h: number;
  r: number;
}

interface NavItem {
  key: string;
  label: string;
  to: string;
  glyph: Glyph[];
  isActive: (pathname: string) => boolean;
}

/** Simple geometric glyphs — ported 1:1 from the design canvas's rail icons (plain SVG rects, no icon library). */
const ITEMS: NavItem[] = [
  {
    key: "library",
    label: "Scenario Library",
    to: "/",
    glyph: [
      { x: 2, y: 2, w: 12, h: 3, r: 0.5 },
      { x: 2, y: 6.5, w: 12, h: 3, r: 0.5 },
      { x: 2, y: 11, w: 12, h: 3, r: 0.5 },
    ],
    isActive: (p) => p === "/",
  },
  {
    key: "dev",
    label: "Scenario Development",
    to: "",
    glyph: [
      { x: 2, y: 2, w: 12, h: 12, r: 1 },
      { x: 5, y: 5, w: 6, h: 6, r: 3 },
    ],
    isActive: (p) => p.startsWith("/scenarios/") && !p.includes("/replay") && !p.includes("/versions/"),
  },
  {
    key: "replay",
    label: "Replay",
    to: "",
    glyph: [
      { x: 2, y: 2, w: 3, h: 12, r: 0.5 },
      { x: 6.5, y: 5, w: 3, h: 9, r: 0.5 },
      { x: 11, y: 8, w: 3, h: 6, r: 0.5 },
    ],
    isActive: (p) => p.includes("/replay"),
  },
  {
    key: "console",
    label: "SDR Console",
    to: "/agents",
    glyph: [
      { x: 1.5, y: 4, w: 13, h: 8, r: 1 },
      { x: 4, y: 12.5, w: 8, h: 1.6, r: 0.8 },
    ],
    isActive: (p) => p.startsWith("/agents"),
  },
  {
    key: "notes",
    label: "Design notes & tokens",
    to: "/notes",
    glyph: [{ x: 3, y: 3, w: 10, h: 10, r: 5 }],
    isActive: (p) => p.startsWith("/notes"),
  },
];

/** Persistent left icon nav rail — the one piece of chrome every page shares. */
export function NavRail() {
  const navigate = useNavigate();
  const location = useLocation();
  const { theme, toggleTheme, density, toggleDensity } = useUiPreferences();

  return (
    <nav
      aria-label="Primary"
      style={{
        width: "var(--nav-width)",
        flex: "0 0 auto",
        background: "var(--rail)",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        padding: "8px 0",
        gap: 2,
        zIndex: 40,
      }}
    >
      <div
        aria-hidden
        style={{
          width: 30,
          height: 30,
          border: "1px solid rgba(255,255,255,.22)",
          display: "grid",
          placeItems: "center",
          marginBottom: 10,
        }}
      >
        <div style={{ width: 10, height: 10, background: "var(--accent)", transform: "rotate(45deg)" }} />
      </div>
      {ITEMS.map((item) => {
        const active = item.isActive(location.pathname);
        return (
          <button
            key={item.key}
            type="button"
            title={item.label}
            aria-label={item.label}
            aria-current={active ? "page" : undefined}
            onClick={() => item.to && navigate(item.to)}
            style={{
              width: 40,
              height: 38,
              display: "grid",
              placeItems: "center",
              background: active ? "rgba(255,255,255,.09)" : "transparent",
              border: "none",
              borderLeft: `2px solid ${active ? "var(--accent)" : "transparent"}`,
              borderRadius: 0,
              color: active ? "#fff" : "var(--rail-ink)",
              padding: 0,
            }}
          >
            <svg width="17" height="17" viewBox="0 0 16 16" aria-hidden="true">
              {item.glyph.map((g, i) => (
                <rect
                  key={i}
                  x={g.x}
                  y={g.y}
                  width={g.w}
                  height={g.h}
                  rx={g.r}
                  style={{ fill: "currentColor" }}
                />
              ))}
            </svg>
          </button>
        );
      })}
      <div style={{ flex: 1 }} />
      <button
        type="button"
        title="Toggle light / dark"
        onClick={toggleTheme}
        style={{
          width: 40,
          height: 34,
          display: "grid",
          placeItems: "center",
          background: "transparent",
          border: "none",
          color: "var(--rail-ink)",
          font: "500 10px/1 var(--mono)",
          letterSpacing: "0.06em",
        }}
      >
        {theme === "dark" ? "LGT" : "DRK"}
      </button>
      <button
        type="button"
        title="Row density"
        onClick={toggleDensity}
        style={{
          width: 40,
          height: 34,
          display: "grid",
          placeItems: "center",
          background: "transparent",
          border: "none",
          color: "var(--rail-ink)",
          font: "500 10px/1 var(--mono)",
        }}
      >
        {density === "compact" ? "≣" : "≡"}
      </button>
    </nav>
  );
}
