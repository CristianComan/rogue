import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { cloneScenario, createScenario, listScenarios } from "../api/scenarios";
import { AppShell } from "../components/shell/AppShell";
import { Badge } from "../components/shell/Badge";
import { CommandButton } from "../components/shell/CommandButton";
import type { GeoPolygon, Scenario } from "../domain/types";

function boundingBoxPolygon(
  minLon: number,
  minLat: number,
  maxLon: number,
  maxLat: number,
): GeoPolygon {
  return {
    type: "Polygon",
    coordinates: [
      [
        [minLon, minLat],
        [maxLon, minLat],
        [maxLon, maxLat],
        [minLon, maxLat],
        [minLon, minLat],
      ],
    ],
  };
}

function StatTile({ label, value, sub }: { label: string; value: number; sub: string }) {
  return (
    <div
      style={{
        background: "var(--surface)",
        border: "1px solid var(--line)",
        borderRadius: 3,
        padding: "11px 13px",
      }}
    >
      <div
        style={{
          font: "500 10.5px/1.2 var(--mono)",
          letterSpacing: "0.08em",
          textTransform: "uppercase",
          color: "var(--ink-3)",
        }}
      >
        {label}
      </div>
      <div style={{ display: "flex", alignItems: "baseline", gap: 7, marginTop: 6 }}>
        <span style={{ fontSize: 23, fontWeight: 600, letterSpacing: "-0.02em" }}>{value}</span>
        <span style={{ fontSize: 11.5, color: "var(--ink-3)" }}>{sub}</span>
      </div>
    </div>
  );
}

/**
 * Scenario library: search/filter, create, clone. Area-of-operation is
 * authored as a bounding box (min/max lon/lat) — drawing it on the map is
 * deferred (see the M3 design note); good enough to get a valid polygon
 * for a new scenario.
 *
 * The design canvas's table also shows Zones/Missions/Links/Duration/
 * Classification columns — those need a per-scenario version fetch (or a
 * classification field the domain model doesn't have at all), so this
 * keeps to columns backed by real data from GET /scenarios alone.
 */
export function ScenarioLibraryPage() {
  const navigate = useNavigate();
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [ownerFilter, setOwnerFilter] = useState("");
  const [tagFilter, setTagFilter] = useState("");
  const [nameFilter, setNameFilter] = useState("");
  const [showNewForm, setShowNewForm] = useState(false);
  const [cloningId, setCloningId] = useState<string | null>(null);

  function refresh() {
    listScenarios({
      owner: ownerFilter || undefined,
      tag: tagFilter || undefined,
      name_contains: nameFilter || undefined,
    })
      .then(setScenarios)
      .catch((e) => setError(String(e)));
  }

  useEffect(refresh, [ownerFilter, tagFilter, nameFilter]);

  const publishedCount = scenarios.filter((s) => s.current_version_id).length;
  const ownerCount = useMemo(() => new Set(scenarios.map((s) => s.owner)).size, [scenarios]);

  return (
    <AppShell
      breadcrumb={[{ label: "ROGUE", to: "/" }, { label: "Scenario Library" }]}
      subnav={{
        pageTitle: "Scenario Library",
        items: [
          { label: "All scenarios", count: scenarios.length, active: true },
          { label: "Published", count: publishedCount },
          { label: "Drafts", count: scenarios.length - publishedCount },
        ],
        footer: "deny-TX default · scenario draft is\nhardware-independent",
      }}
      actions={
        <CommandButton label="+ New scenario" variant="accent" onClick={() => setShowNewForm((v) => !v)} />
      }
    >
      <div style={{ padding: "16px 18px 24px", display: "flex", flexDirection: "column", gap: 14 }}>
        <div style={{ display: "flex", alignItems: "flex-end", justifyContent: "space-between", gap: 16 }}>
          <div>
            <div style={{ fontSize: 20, fontWeight: 600, letterSpacing: "-0.01em" }}>Scenario Library</div>
            <div style={{ fontSize: 12.5, color: "var(--ink-2)", marginTop: 3 }}>
              Hardware-independent scenario drafts and published immutable versions.
            </div>
          </div>
          <div style={{ display: "flex", gap: 6 }}>
            <input
              placeholder="Owner"
              value={ownerFilter}
              onChange={(e) => setOwnerFilter(e.target.value)}
              style={{ height: 28, fontSize: 12.5 }}
            />
            <input
              placeholder="Tag"
              value={tagFilter}
              onChange={(e) => setTagFilter(e.target.value)}
              style={{ height: 28, fontSize: 12.5 }}
            />
            <input
              placeholder="Name contains…"
              value={nameFilter}
              onChange={(e) => setNameFilter(e.target.value)}
              style={{ height: 28, width: 200, fontSize: 12.5 }}
            />
          </div>
        </div>

        {error && (
          <div
            style={{
              padding: "8px 12px",
              background: "var(--bad-bg)",
              color: "var(--bad-fg)",
              border: "1px solid var(--bad-bd)",
              borderRadius: 3,
              fontSize: 13,
            }}
          >
            {error}
          </div>
        )}

        {showNewForm && (
          <NewScenarioForm
            onCreated={(scenario) => {
              setShowNewForm(false);
              navigate(`/scenarios/${scenario.id}`);
            }}
          />
        )}

        <div style={{ display: "grid", gridTemplateColumns: "repeat(4,minmax(0,1fr))", gap: 10 }}>
          <StatTile label="Scenarios" value={scenarios.length} sub="total" />
          <StatTile label="Published" value={publishedCount} sub="immutable versions" />
          <StatTile label="Drafts" value={scenarios.length - publishedCount} sub="unpublished" />
          <StatTile label="Owners" value={ownerCount} sub="distinct" />
        </div>

        <div
          style={{
            background: "var(--surface)",
            border: "1px solid var(--line)",
            borderRadius: 3,
            overflow: "hidden",
          }}
        >
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              padding: "8px 12px",
              borderBottom: "1px solid var(--line)",
              background: "var(--surface-2)",
            }}
          >
            <div
              style={{
                font: "600 11px/1.2 var(--mono)",
                letterSpacing: "0.09em",
                textTransform: "uppercase",
                color: "var(--ink-3)",
              }}
            >
              All scenarios
            </div>
            <div style={{ fontSize: 11.5, color: "var(--ink-3)" }}>
              {scenarios.length} items · click a row for details
            </div>
          </div>
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "2.2fr .8fr .9fr 1fr",
              alignItems: "center",
              padding: "0 12px",
              height: 30,
              borderBottom: "1px solid var(--line)",
              background: "var(--surface-2)",
              font: "500 10.5px/1 var(--mono)",
              letterSpacing: "0.06em",
              textTransform: "uppercase",
              color: "var(--ink-3)",
            }}
          >
            <div>Scenario</div>
            <div>Owner</div>
            <div>Tags</div>
            <div>State</div>
          </div>
          {scenarios.map((s) => (
            <div
              key={s.id}
              onClick={() => navigate(`/scenarios/${s.id}`)}
              style={{
                display: "grid",
                gridTemplateColumns: "2.2fr .8fr .9fr 1fr",
                alignItems: "center",
                padding: "var(--rp) 12px",
                borderBottom: "1px solid var(--line)",
                cursor: "pointer",
              }}
            >
              <div style={{ minWidth: 0 }}>
                <div
                  style={{
                    fontWeight: 600,
                    fontSize: 12.5,
                    whiteSpace: "nowrap",
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                  }}
                >
                  {s.name}
                </div>
                <div
                  style={{
                    font: "400 11px/1.4 var(--mono)",
                    color: "var(--ink-3)",
                    whiteSpace: "nowrap",
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                  }}
                >
                  {s.id} {s.tags.length > 0 ? `· ${s.tags.join(", ")}` : ""}
                </div>
              </div>
              <div style={{ color: "var(--ink-2)", fontSize: 12.5 }}>{s.owner}</div>
              <div style={{ color: "var(--ink-2)", fontSize: 12.5 }}>{s.tags.join(", ") || "—"}</div>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8 }}>
                <Badge tone={s.current_version_id ? "ok" : "mute"}>
                  {s.current_version_id ? "published" : "draft"}
                </Badge>
                <div style={{ display: "flex", gap: 6 }} onClick={(e) => e.stopPropagation()}>
                  <button type="button" onClick={() => setCloningId(s.id)}>
                    Clone
                  </button>
                  <button type="button" onClick={() => navigate(`/scenarios/${s.id}/replay`)}>
                    Replay
                  </button>
                </div>
              </div>
            </div>
          ))}
          {scenarios.length === 0 && (
            <div style={{ padding: 20, textAlign: "center", color: "var(--ink-3)", fontSize: 13 }}>
              No scenarios match these filters.
            </div>
          )}
        </div>

        {cloningId && (
          <CloneScenarioForm
            sourceScenarioId={cloningId}
            onCloned={(result) => navigate(`/scenarios/${result.scenario_id}`)}
            onCancel={() => setCloningId(null)}
          />
        )}
      </div>
    </AppShell>
  );
}

function NewScenarioForm({ onCreated }: { onCreated: (scenario: Scenario) => void }) {
  const [name, setName] = useState("");
  const [owner, setOwner] = useState("");
  const [tags, setTags] = useState("");
  const [minLon, setMinLon] = useState(13.0);
  const [minLat, setMinLat] = useState(52.0);
  const [maxLon, setMaxLon] = useState(13.6);
  const [maxLat, setMaxLat] = useState(52.6);
  const [error, setError] = useState<string | null>(null);

  async function submit() {
    setError(null);
    try {
      const scenario = await createScenario({
        name,
        owner,
        tags: tags
          .split(",")
          .map((t) => t.trim())
          .filter(Boolean),
        area_of_operation: boundingBoxPolygon(minLon, minLat, maxLon, maxLat),
      });
      onCreated(scenario);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  return (
    <div style={{ background: "var(--surface)", border: "1px solid var(--line)", borderRadius: 3 }}>
      <div
        style={{
          padding: "8px 12px",
          borderBottom: "1px solid var(--line)",
          background: "var(--surface-2)",
          font: "600 11px/1.2 var(--mono)",
          letterSpacing: "0.09em",
          textTransform: "uppercase",
          color: "var(--ink-3)",
        }}
      >
        New scenario
      </div>
      <div
        data-testid="new-scenario-form"
        style={{ padding: 12, display: "flex", flexDirection: "column", gap: 8 }}
      >
        <input placeholder="Name" value={name} onChange={(e) => setName(e.target.value)} />
        <input placeholder="Owner" value={owner} onChange={(e) => setOwner(e.target.value)} />
        <input
          placeholder="Tags (comma separated)"
          value={tags}
          onChange={(e) => setTags(e.target.value)}
        />
        <div style={{ display: "flex", gap: 8 }}>
          <input
            type="number"
            step={0.01}
            value={minLon}
            onChange={(e) => setMinLon(Number(e.target.value))}
          />
          <input
            type="number"
            step={0.01}
            value={minLat}
            onChange={(e) => setMinLat(Number(e.target.value))}
          />
          <input
            type="number"
            step={0.01}
            value={maxLon}
            onChange={(e) => setMaxLon(Number(e.target.value))}
          />
          <input
            type="number"
            step={0.01}
            value={maxLat}
            onChange={(e) => setMaxLat(Number(e.target.value))}
          />
        </div>
        {error && <span style={{ color: "var(--bad-fg)", fontSize: 12 }}>{error}</span>}
        <div>
          <button type="button" data-variant="primary" onClick={submit} disabled={!name || !owner}>
            Create
          </button>
        </div>
      </div>
    </div>
  );
}

function CloneScenarioForm({
  sourceScenarioId,
  onCloned,
  onCancel,
}: {
  sourceScenarioId: string;
  onCloned: (result: { scenario_id: string; draft_id: string }) => void;
  onCancel: () => void;
}) {
  const [name, setName] = useState("");
  const [owner, setOwner] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function submit() {
    setError(null);
    try {
      onCloned(await cloneScenario(sourceScenarioId, { name, owner }));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  return (
    <div
      role="dialog"
      aria-label="Clone scenario"
      style={{
        position: "fixed",
        inset: 0,
        background: "var(--surface-overlay)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 10,
      }}
    >
      <div
        style={{
          width: 340,
          background: "var(--surface)",
          border: "1px solid var(--line)",
          borderRadius: 3,
        }}
      >
        <div
          style={{
            padding: "8px 12px",
            borderBottom: "1px solid var(--line)",
            background: "var(--surface-2)",
            font: "600 11px/1.2 var(--mono)",
            letterSpacing: "0.09em",
            textTransform: "uppercase",
            color: "var(--ink-3)",
          }}
        >
          Clone scenario
        </div>
        <div style={{ padding: 12, display: "flex", flexDirection: "column", gap: 8 }}>
          <input placeholder="New name" value={name} onChange={(e) => setName(e.target.value)} />
          <input placeholder="Owner" value={owner} onChange={(e) => setOwner(e.target.value)} />
          {error && <span style={{ color: "var(--bad-fg)", fontSize: 12 }}>{error}</span>}
          <div style={{ display: "flex", gap: 8 }}>
            <button type="button" data-variant="primary" onClick={submit} disabled={!name || !owner}>
              Clone
            </button>
            <button type="button" onClick={onCancel}>
              Cancel
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
