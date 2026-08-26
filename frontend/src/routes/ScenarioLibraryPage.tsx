import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { cloneScenario, createScenario, listScenarios } from "../api/scenarios";
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
    <div style={{ padding: 16, maxWidth: 800, margin: "0 auto" }}>
      <h1>ROGUE Scenarios</h1>
      <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
        <input
          placeholder="Owner"
          value={ownerFilter}
          onChange={(e) => setOwnerFilter(e.target.value)}
        />
        <input placeholder="Tag" value={tagFilter} onChange={(e) => setTagFilter(e.target.value)} />
        <input
          placeholder="Name contains…"
          value={nameFilter}
          onChange={(e) => setNameFilter(e.target.value)}
        />
        <button type="button" onClick={() => setShowNewForm((v) => !v)}>
          + New scenario
        </button>
      </div>
      {error && <p style={{ color: "crimson" }}>{error}</p>}

      {showNewForm && (
        <NewScenarioForm
          onCreated={(scenario) => {
            setShowNewForm(false);
            navigate(`/scenarios/${scenario.id}`);
          }}
        />
      )}

      <table style={{ width: "100%", borderCollapse: "collapse", marginTop: 16 }}>
        <thead>
          <tr style={{ textAlign: "left", borderBottom: "1px solid #ccc" }}>
            <th>Name</th>
            <th>Owner</th>
            <th>Tags</th>
            <th>Current version</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {scenarios.map((s) => (
            <tr key={s.id} style={{ borderBottom: "1px solid #eee" }}>
              <td>{s.name}</td>
              <td>{s.owner}</td>
              <td>{s.tags.join(", ")}</td>
              <td>{s.current_version_id ? "published" : "unpublished"}</td>
              <td style={{ display: "flex", gap: 6 }}>
                <button type="button" onClick={() => navigate(`/scenarios/${s.id}`)}>
                  Edit
                </button>
                <button type="button" onClick={() => setCloningId(s.id)}>
                  Clone
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {cloningId && (
        <CloneScenarioForm
          sourceScenarioId={cloningId}
          onCloned={(result) => navigate(`/scenarios/${result.scenario_id}`)}
          onCancel={() => setCloningId(null)}
        />
      )}
    </div>
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
    <div
      data-testid="new-scenario-form"
      style={{
        border: "1px solid #ccc",
        padding: 12,
        marginBottom: 16,
        display: "flex",
        flexDirection: "column",
        gap: 8,
      }}
    >
      <h3 style={{ margin: 0 }}>New scenario</h3>
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
      {error && <span style={{ color: "crimson" }}>{error}</span>}
      <button type="button" onClick={submit} disabled={!name || !owner}>
        Create
      </button>
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
        background: "rgba(0,0,0,0.4)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
      }}
    >
      <div
        style={{
          background: "#fff",
          padding: 16,
          display: "flex",
          flexDirection: "column",
          gap: 8,
          width: 320,
        }}
      >
        <h3 style={{ margin: 0 }}>Clone scenario</h3>
        <input placeholder="New name" value={name} onChange={(e) => setName(e.target.value)} />
        <input placeholder="Owner" value={owner} onChange={(e) => setOwner(e.target.value)} />
        {error && <span style={{ color: "crimson" }}>{error}</span>}
        <div style={{ display: "flex", gap: 8 }}>
          <button type="button" onClick={submit} disabled={!name || !owner}>
            Clone
          </button>
          <button type="button" onClick={onCancel}>
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
}
