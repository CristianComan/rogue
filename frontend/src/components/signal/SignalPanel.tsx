import { Waterfall } from "../timeline/Waterfall";
import type { DroneMission, IQRecording } from "../../domain/types";
import type { Selection } from "../../state/selection";
import { Badge } from "../shell/Badge";
import { Card } from "../shell/Card";
import { SignalTimeline } from "./SignalTimeline";

function khzOrMhz(hz: number): string {
  return hz >= 1e6 ? `${(hz / 1e6).toFixed(1)} MS/s` : `${(hz / 1e3).toFixed(0)} kS/s`;
}

const ACCESS_TONE = { public: "ok", restricted: "warn", controlled: "bad" } as const;

/**
 * "What transmits and when" — every RF link across the scenario laid out as
 * a Gantt timeline (SignalTimeline), the real SigMF recording catalogue
 * available to bind against, and each active link's real waterfall
 * spectrogram. Previously this content was split across a plain table and a
 * separate linear spectrum-bar strip; the Gantt view replaces both with one
 * picture of authored intent against the shared scenario-time axis.
 */
export function SignalPanel({
  missions,
  maxSeconds,
  selection,
  onSelect,
  catalogue,
}: {
  missions: DroneMission[];
  maxSeconds: number;
  selection: Selection;
  onSelect: (selection: Selection) => void;
  catalogue: IQRecording[];
}) {
  return (
    <Card
      title="Signal Knowledge"
      actions={
        <span style={{ font: "400 11px/1 var(--mono)", color: "var(--ink-3)" }}>
          what transmits, and when
        </span>
      }
      noPadding
      style={{ height: "100%" }}
      bodyStyle={{ overflowY: "auto" }}
    >
      <SignalTimeline
        missions={missions}
        maxSeconds={maxSeconds}
        catalogue={catalogue}
        selection={selection}
        onSelect={onSelect}
      />

      <div
        style={{
          padding: "9px 10px 5px",
          font: "500 10.5px/1 var(--mono)",
          letterSpacing: "0.07em",
          textTransform: "uppercase",
          color: "var(--ink-3)",
        }}
      >
        Recording catalogue (SigMF) — {catalogue.length}
      </div>
      {catalogue.length === 0 ? (
        <div style={{ padding: "0 10px 10px", fontSize: 12, color: "var(--ink-3)" }}>
          No recordings in the catalogue yet.
        </div>
      ) : (
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 11.5 }}>
            <thead>
              <tr
                style={{
                  background: "var(--surface-2)",
                  borderTop: "1px solid var(--line)",
                  borderBottom: "1px solid var(--line)",
                }}
              >
                {["Recording", "Sample rate", "Dur", "Center freq", "Access"].map((h) => (
                  <th
                    key={h}
                    style={{
                      textAlign: "left",
                      padding: "4px 10px",
                      font: "500 10px/1 var(--mono)",
                      letterSpacing: "0.06em",
                      textTransform: "uppercase",
                      color: "var(--ink-3)",
                    }}
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {catalogue.map((r) => (
                <tr key={`${r.id}:${r.version}`} style={{ borderBottom: "1px solid var(--line)" }}>
                  <td
                    style={{
                      padding: "var(--rp) 10px",
                      maxWidth: 260,
                      whiteSpace: "nowrap",
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                      color: "var(--ink)",
                    }}
                  >
                    {r.metadata_object_key.split("/").pop()}
                  </td>
                  <td style={{ padding: "var(--rp) 10px" }}>{khzOrMhz(r.sample_rate_hz)}</td>
                  <td style={{ padding: "var(--rp) 10px" }}>{r.duration_s.toFixed(1)}s</td>
                  <td style={{ padding: "var(--rp) 10px" }}>
                    {r.center_frequency_hz !== null
                      ? `${(r.center_frequency_hz / 1e6).toFixed(1)} MHz`
                      : "—"}
                  </td>
                  <td style={{ padding: "var(--rp) 10px" }}>
                    <Badge tone={ACCESS_TONE[r.access_classification]}>
                      {r.access_classification}
                    </Badge>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div style={{ display: "flex", flexWrap: "wrap" }}>
        {missions.flatMap((mission) =>
          mission.rf_links.map((link) => (
            <Waterfall key={link.id} link={link} missionName={mission.name} catalogue={catalogue} />
          )),
        )}
      </div>
    </Card>
  );
}
