import { useRunTime } from "../../state/runTimeContext";
import { colors, monoFontStack, sectionHeadingStyle } from "../../styles/tokens";
import type { RunEvent } from "../../domain/run";

const CRITICAL_KINDS = new Set(["error", "emergency_stopped"]);

function eventColor(event: RunEvent): string {
  if (CRITICAL_KINDS.has(event.kind)) return colors.severity.critical;
  if (event.severity === "blocking") return colors.severity.blocking;
  if (event.severity === "warning") return colors.severity.warning;
  return colors.severity.info;
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

  return (
    <div style={{ fontFamily: monoFontStack, fontSize: 12 }}>
      <div style={{ ...sectionHeadingStyle, padding: "8px 12px 4px" }}>Watchdog & safety feed</div>
      {sorted.length === 0 && (
        <div style={{ padding: "0 12px 8px", color: colors.textMuted }}>
          No events recorded yet.
        </div>
      )}
      <div style={{ maxHeight: 260, overflowY: "auto" }}>
        {sorted.map((event) => (
          <div
            key={event.id}
            style={{
              display: "flex",
              gap: 8,
              padding: "4px 12px",
              borderLeft: `3px solid ${eventColor(event)}`,
            }}
          >
            <span style={{ color: colors.textMuted, whiteSpace: "nowrap" }}>
              {new Date(event.at).toLocaleTimeString()}
            </span>
            <span style={{ color: eventColor(event), fontWeight: 700, whiteSpace: "nowrap" }}>
              {eventLabel(event)}
            </span>
            <span style={{ color: colors.textMuted, whiteSpace: "nowrap" }}>
              {event.device_id
                ? `${event.device_id}${event.channel_index !== null ? `/ch${event.channel_index}` : ""}`
                : event.kind}
            </span>
            <span>{event.message}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
