import { AppShell } from "../components/shell/AppShell";
import { Card } from "../components/shell/Card";

const SYNC_NOTES: { k: string; v: string }[] = [
  {
    k: "one clock",
    v: "Development holds a single authoring scrub time T. The map evaluator, the Signal-panel playhead, and the Doppler sub-view all read the same T — nothing keeps its own cursor.",
  },
  {
    k: "replay ≠ dev",
    v: "Replay runs on run time from the run manifest, uses square red-accented run controls, and never exposes an authoring scrub — the two pages share evaluator code, not state.",
  },
  {
    k: "events",
    v: "Timeline events are the only writers of T besides the scrub itself — clicking an event seeks and pauses. Spatially-referenced events resolve their time from the trajectory, absolute ones are pinned.",
  },
  {
    k: "coherent groups",
    v: "Detection-only receivers get one physical channel per drone signal. AOA/TDOA receivers need a parallel coherent group — allocated, leased, armed and muted as one atomic unit, never partial.",
  },
  {
    k: "hardware-independent",
    v: "Scenarios never bind to a physical device or channel. Hardware binding is resolved only at compile time, into the immutable Replay Plan.",
  },
];

const COMPONENT_INDEX: { k: string; v: string }[] = [
  { k: "NavRail", v: "Persistent 52px dark icon rail — page switch, theme toggle, row density toggle." },
  { k: "Subnav", v: "Collapsible 206px secondary panel — page title + subsection list with counts." },
  { k: "TopBar", v: "Breadcrumb + page commands, toggles Subnav via the hamburger button." },
  { k: "Card", v: "Bordered panel, optional label/actions header or a fully custom header row." },
  { k: "Badge", v: "Rounded status pill with a dot, bound to the ok/warn/bad/info/mute tone system." },
  { k: "CommandButton", v: "Dot+label top-bar action button — accent for the primary command, ghost otherwise." },
];

const TOKEN_ROWS: { name: string; light: string; dark: string }[] = [
  { name: "--bg", light: "#efeeec", dark: "#121110" },
  { name: "--surface", light: "#ffffff", dark: "#1b1a19" },
  { name: "--line", light: "#e0dedb", dark: "#332f2d" },
  { name: "--ink", light: "#1c1b19", dark: "#f1efec" },
  { name: "--ink-2", light: "#575450", dark: "#b3ada7" },
  { name: "--ink-3", light: "#8b8781", dark: "#807a74" },
  { name: "--accent", light: "oklch(.52 .13 245)", dark: "oklch(.72 .12 245)" },
  { name: "--ok-fg", light: "oklch(.44 .11 150)", dark: "oklch(.82 .12 150)" },
  { name: "--warn-fg", light: "oklch(.46 .11 65)", dark: "oklch(.84 .12 80)" },
  { name: "--bad-fg", light: "oklch(.48 .15 25)", dark: "oklch(.78 .14 25)" },
  { name: "--info-fg", light: "oklch(.46 .12 245)", dark: "oklch(.82 .10 245)" },
  { name: "--mute-fg", light: "#6c6864", dark: "#9b958f" },
];

function NoteRow({ k, v }: { k: string; v: string }) {
  return (
    <div style={{ display: "grid", gridTemplateColumns: "96px minmax(0,1fr)", gap: 12 }}>
      <span
        style={{
          font: "600 10.5px/1.5 var(--mono)",
          letterSpacing: "0.05em",
          textTransform: "uppercase",
          color: "var(--ink-3)",
        }}
      >
        {k}
      </span>
      <span style={{ fontSize: 12.5, lineHeight: 1.55, color: "var(--ink-2)" }}>{v}</span>
    </div>
  );
}

/** A living style guide — the design canvas's own "Notes" page, ported directly (sync model + component index + theme tokens). */
export function NotesPage() {
  return (
    <AppShell breadcrumb={[{ label: "ROGUE", to: "/" }, { label: "Design notes" }]}>
      <div
        style={{
          padding: "16px 18px 28px",
          display: "grid",
          gridTemplateColumns: "minmax(0,1.1fr) minmax(0,1fr)",
          gap: 14,
          alignItems: "start",
        }}
      >
        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          <Card title="Sync model — map · scrub · panels">
            <div style={{ display: "flex", flexDirection: "column", gap: 9 }}>
              {SYNC_NOTES.map((n) => (
                <NoteRow key={n.k} {...n} />
              ))}
            </div>
          </Card>
          <Card title="Component index" noPadding>
            {COMPONENT_INDEX.map((c) => (
              <div
                key={c.k}
                style={{
                  display: "grid",
                  gridTemplateColumns: "190px minmax(0,1fr)",
                  gap: 12,
                  padding: "8px 14px",
                  borderBottom: "1px solid var(--line)",
                  fontSize: 12,
                }}
              >
                <span style={{ font: "500 11.5px/1.4 var(--mono)", color: "var(--ink)" }}>{c.k}</span>
                <span style={{ color: "var(--ink-2)", lineHeight: 1.5 }}>{c.v}</span>
              </div>
            ))}
          </Card>
        </div>

        <Card
          noPadding
          header={
            <>
              <span
                style={{
                  font: "600 11px/1.2 var(--mono)",
                  letterSpacing: "0.09em",
                  textTransform: "uppercase",
                  color: "var(--ink-3)",
                }}
              >
                Theme tokens
              </span>
              <span style={{ marginLeft: "auto", font: "400 10.5px/1 var(--mono)", color: "var(--ink-3)" }}>
                light / dark
              </span>
            </>
          }
        >
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "1.1fr .9fr .9fr 34px",
              padding: "5px 12px",
              background: "var(--surface-2)",
              borderBottom: "1px solid var(--line)",
              font: "500 10px/1 var(--mono)",
              letterSpacing: "0.06em",
              textTransform: "uppercase",
              color: "var(--ink-3)",
            }}
          >
            <div>Token</div>
            <div>Light</div>
            <div>Dark</div>
            <div />
          </div>
          {TOKEN_ROWS.map((tk) => (
            <div
              key={tk.name}
              style={{
                display: "grid",
                gridTemplateColumns: "1.1fr .9fr .9fr 34px",
                padding: "4px 12px",
                borderBottom: "1px solid var(--line)",
                alignItems: "center",
                font: "400 11px/1.5 var(--mono)",
                color: "var(--ink-2)",
              }}
            >
              <div style={{ color: "var(--ink)" }}>{tk.name}</div>
              <div>{tk.light}</div>
              <div>{tk.dark}</div>
              <div
                style={{
                  justifySelf: "end",
                  width: 18,
                  height: 14,
                  border: "1px solid var(--line-2)",
                  background: `var(${tk.name})`,
                }}
              />
            </div>
          ))}
          <div style={{ padding: "9px 12px", font: "400 11px/1.6 var(--mono)", color: "var(--ink-3)" }}>
            Spacing 4/8px scale · radius 2px · 1px borders, no elevation except blades (0 0 0 1px +
            24px/-8px shadow).
          </div>
        </Card>
      </div>
    </AppShell>
  );
}
