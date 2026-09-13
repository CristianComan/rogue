import { useRunTime } from "../../state/runTimeContext";
import { toneVars, type Tone } from "../../styles/tokens";
import type { RunEvent } from "../../domain/run";

const CRITICAL_KINDS = new Set(["error", "emergency_stopped"]);

function eventTone(event: RunEvent): Tone {
  if (CRITICAL_KINDS.has(event.kind)) return "bad";
  if (event.severity === "blocking") return "bad";
  if (event.severity === "warning") return "warn";
  return "info";
}

function eventLabel(event: RunEvent): string {
  if (CRITICAL_KINDS.has(event.kind)) return "CRITICAL";
  return event.severity.toUpperCase();
}

/**
 * The run's real, append-only evidence log (ScenarioRun.events) rendered as
 * an activity feed — this *is* the watchdog/safety feed; there is no
 * predictive layer yet (lease_sweep is reactive/expiry-based today), so
 * only events that actually happened are shown, newest first.
 */
export function WatchdogFeed() {
  const { run } = useRunTime();
  const sorted = [...run.events].sort((a, b) => b.sequence - a.sequence);
  const isLive = run.status === "running" || run.status === "armed";

  return (
    <div style={{ font: "400 11.5px/1.4 var(--mono)" }}>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 8,
          padding: "8px 12px",
          borderBottom: "1px solid var(--line)",
          font: "600 11px/1 var(--mono)",
          letterSpacing: "0.04em",
        }}
      >
        Watchdog &amp; safety feed
        {isLive && (
          <span
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: 4,
              color: "var(--ok-fg)",
              fontWeight: 500,
            }}
          >
            <span
              aria-hidden
              style={{
                width: 6,
                height: 6,
                borderRadius: "50%",
                background: "var(--ok-fg)",
                animation: "livepulse 1.6s ease-in-out infinite",
              }}
            />
            live
          </span>
        )}
      </div>
      {sorted.length === 0 && (
        <div style={{ padding: "8px 12px", color: "var(--ink-3)" }}>No events recorded yet.</div>
      )}
      <div style={{ maxHeight: 260, overflowY: "auto" }}>
        {sorted.map((event) => {
          const vars = toneVars(eventTone(event));
          return (
            <div
              key={event.id}
              style={{
                display: "flex",
                gap: 8,
                padding: "4px 12px",
                borderLeft: `3px solid ${vars.bd}`,
              }}
            >
              <span style={{ color: "var(--ink-3)", whiteSpace: "nowrap" }}>
                {new Date(event.at).toLocaleTimeString()}
              </span>
              <span style={{ color: vars.fg, fontWeight: 600, whiteSpace: "nowrap" }}>
                {eventLabel(event)}
              </span>
              <span style={{ color: "var(--ink-3)", whiteSpace: "nowrap" }}>
                {event.device_id
                  ? `${event.device_id}${event.channel_index !== null ? `/ch${event.channel_index}` : ""}`
                  : event.kind}
              </span>
              <span>{event.message}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
