import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { cloneScenario, createScenario, listScenarios } from "../api/scenarios";
import { AppShell } from "../components/shell/AppShell";
import { Badge } from "../components/shell/Badge";
import { Card } from "../components/shell/Card";
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

/**
 * Scenario library: search/filter, create, clone. Area-of-operation is
 * authored as a bounding box (min/max lon/lat) — drawing it on the map is
 * deferred (see the M3 design note); good enough to get a valid polygon
 * for a new scenario.
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

  return (
    <AppShell
      breadcrumb={[{ label: "Scenario Library" }]}
      actions={
        <button type="button" data-variant="primary" onClick={() => setShowNewForm((v) => !v)}>
          + New scenario
        </button>
      }
    >
      <div
        style={{
          padding: 20,
          maxWidth: 1000,
          margin: "0 auto",
          display: "flex",
          flexDirection: "column",
          gap: 16,
        }}
      >
        {error && (
          <div
            style={{
              padding: "8px 12px",
              background: "var(--status-danger-bg)",
              color: "var(--status-danger)",
              borderRadius: "var(--radius)",
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

        <Card
          title="Scenarios"
          actions={
            <div style={{ display: "flex", gap: 6 }}>
              <input
                placeholder="Owner"
                value={ownerFilter}
                onChange={(e) => setOwnerFilter(e.target.value)}
                style={{ fontSize: 12, padding: "4px 8px" }}
              />
              <input
                placeholder="Tag"
                value={tagFilter}
                onChange={(e) => setTagFilter(e.target.value)}
                style={{ fontSize: 12, padding: "4px 8px" }}
              />
              <input
                placeholder="Name contains…"
                value={nameFilter}
                onChange={(e) => setNameFilter(e.target.value)}
                style={{ fontSize: 12, padding: "4px 8px" }}
              />
            </div>
          }
          noPadding
        >
          <table style={{ width: "100%", fontSize: 13 }}>
            <thead>
              <tr style={{ textAlign: "left", borderBottom: "1px solid var(--border-default)" }}>
                {["Name", "Owner", "Tags", "Version", ""].map((h) => (
                  <th
                    key={h}
                    style={{
                      padding: "8px 14px",
                      fontSize: 11,
                      fontWeight: 600,
                      letterSpacing: "0.04em",
                      textTransform: "uppercase",
                      color: "var(--text-secondary)",
                    }}
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {scenarios.map((s) => (
                <tr key={s.id} style={{ borderBottom: "1px solid var(--border-subtle)" }}>
                  <td style={{ padding: "8px 14px", fontWeight: 500 }}>{s.name}</td>
                  <td style={{ padding: "8px 14px", color: "var(--text-secondary)" }}>{s.owner}</td>
                  <td style={{ padding: "8px 14px", color: "var(--text-secondary)" }}>
                    {s.tags.join(", ")}
                  </td>
                  <td style={{ padding: "8px 14px" }}>
                    <Badge tone={s.current_version_id ? "success" : "neutral"}>
                      {s.current_version_id ? "Published" : "Unpublished"}
                    </Badge>
                  </td>
                  <td
                    style={{
                      padding: "8px 14px",
                      display: "flex",
                      gap: 6,
                      justifyContent: "flex-end",
                    }}
                  >
                    <button type="button" onClick={() => navigate(`/scenarios/${s.id}`)}>
                      Edit
                    </button>
                    <button type="button" onClick={() => setCloningId(s.id)}>
                      Clone
                    </button>
                    <button type="button" onClick={() => navigate(`/scenarios/${s.id}/replay`)}>
                      Replay
                    </button>
                  </td>
                </tr>
              ))}
              {scenarios.length === 0 && (
                <tr>
                  <td
                    colSpan={5}
                    style={{ padding: 20, textAlign: "center", color: "var(--text-tertiary)" }}
                  >
                    No scenarios match these filters.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </Card>

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
    <Card title="New scenario">
      <div
        data-testid="new-scenario-form"
        style={{ display: "flex", flexDirection: "column", gap: 8 }}
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
        {error && <span style={{ color: "var(--status-danger)", fontSize: 12 }}>{error}</span>}
        <div>
          <button type="button" data-variant="primary" onClick={submit} disabled={!name || !owner}>
            Create
          </button>
        </div>
      </div>
    </Card>
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
      <div style={{ width: 340 }}>
        <Card title="Clone scenario">
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            <input placeholder="New name" value={name} onChange={(e) => setName(e.target.value)} />
            <input placeholder="Owner" value={owner} onChange={(e) => setOwner(e.target.value)} />
            {error && <span style={{ color: "var(--status-danger)", fontSize: 12 }}>{error}</span>}
            <div style={{ display: "flex", gap: 8 }}>
              <button
                type="button"
                data-variant="primary"
                onClick={submit}
                disabled={!name || !owner}
              >
                Clone
              </button>
              <button type="button" onClick={onCancel}>
                Cancel
              </button>
            </div>
          </div>
        </Card>
      </div>
    </div>
  );
}
