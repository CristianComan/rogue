import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";

export type Theme = "light" | "dark";
export type Density = "compact" | "cosy";

interface UiPreferencesValue {
  theme: Theme;
  toggleTheme: () => void;
  density: Density;
  toggleDensity: () => void;
  /** Whether the secondary sub-nav panel is expanded — lives here (not per-page) so it survives navigation. */
  navOpen: boolean;
  toggleNav: () => void;
}

const UiPreferencesContext = createContext<UiPreferencesValue | null>(null);

const STORAGE_KEY = "rogue-ui-preferences";

function loadInitial(): { theme: Theme; density: Density } {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw);
      if (parsed.theme === "light" || parsed.theme === "dark") {
        return { theme: parsed.theme, density: parsed.density === "cosy" ? "cosy" : "compact" };
      }
    }
  } catch {
    // Corrupt/unavailable storage falls back to the default below.
  }
  return { theme: "light", density: "compact" };
}

/**
 * Wraps the whole app (outside <Routes>, in App.tsx) so the theme/density/
 * nav-open toggles in NavRail survive client-side navigation between pages
 * — each page's own AppShell/NavRail instance is a fresh mount, but this
 * provider isn't.
 */
export function UiPreferencesProvider({ children }: { children: ReactNode }) {
  const initial = loadInitial();
  const [theme, setTheme] = useState<Theme>(initial.theme);
  const [density, setDensity] = useState<Density>(initial.density);
  const [navOpen, setNavOpen] = useState(true);

  useEffect(() => {
    document.documentElement.setAttribute("data-rogue-theme", theme);
    document.documentElement.style.setProperty("--rp", density === "compact" ? "7px" : "11px");
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify({ theme, density }));
    } catch {
      // Best-effort persistence only — a per-viewer convenience, not load-bearing.
    }
  }, [theme, density]);

  const toggleTheme = useCallback(() => setTheme((t) => (t === "dark" ? "light" : "dark")), []);
  const toggleDensity = useCallback(
    () => setDensity((d) => (d === "compact" ? "cosy" : "compact")),
    [],
  );
  const toggleNav = useCallback(() => setNavOpen((v) => !v), []);

  return (
    <UiPreferencesContext.Provider
      value={{ theme, toggleTheme, density, toggleDensity, navOpen, toggleNav }}
    >
      {children}
    </UiPreferencesContext.Provider>
  );
}

export function useUiPreferences(): UiPreferencesValue {
  const ctx = useContext(UiPreferencesContext);
  if (!ctx) throw new Error("useUiPreferences must be used within a UiPreferencesProvider");
  return ctx;
}
