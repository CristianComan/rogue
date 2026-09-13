import { useRunTime } from "../../state/runTimeContext";
import type { DeviceLease } from "../../domain/run";

function leaseFraction(lease: DeviceLease, nowMs: number): number {
  const total = new Date(lease.expires_at).getTime() - new Date(lease.leased_at).getTime();
  const remaining = new Date(lease.expires_at).getTime() - nowMs;
  if (total <= 0) return 0;
  return Math.max(0, Math.min(1, remaining / total));
}

/**
 * Real DeviceLease progress bars (backend/rogue/domain/run.py) — the
 * companion panel to the Watchdog feed, since a lease's countdown is the
 * safety mechanism the watchdog feed's expiry-related events describe
 * after the fact. Bar fraction is remaining/total lease lifetime, not a
 * fixed visual scale, so a short lease reads the same urgency as a long
 * one nearing expiry.
 */
export function LeasesPanel() {
  const { run, nowMs } = useRunTime();
  const leases = [...run.device_leases].sort(
    (a, b) => new Date(a.expires_at).getTime() - new Date(b.expires_at).getTime(),
  );

  return (
    <div style={{ font: "400 11.5px/1.4 var(--mono)" }}>
      <div
        style={{
          padding: "8px 12px",
          borderBottom: "1px solid var(--line)",
          font: "600 11px/1 var(--mono)",
          letterSpacing: "0.04em",
        }}
      >
        Device leases — {leases.length}
      </div>
      {leases.length === 0 && (
        <div style={{ padding: "8px 12px", color: "var(--ink-3)" }}>No active leases.</div>
      )}
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          gap: 8,
          padding: leases.length ? "10px 12px" : 0,
        }}
      >
        {leases.map((lease) => {
          const fraction = leaseFraction(lease, nowMs);
          const secondsLeft = Math.max(0, (new Date(lease.expires_at).getTime() - nowMs) / 1000);
          const tone = secondsLeft < 30 ? "var(--warn-fg)" : "var(--accent)";
          return (
            <div key={lease.id}>
              <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 3 }}>
                <span>
                  {lease.device_id} / ch{lease.channel_index}
                </span>
                <span style={{ color: "var(--ink-3)" }}>{Math.floor(secondsLeft)}s</span>
              </div>
              <div
                style={{
                  height: 4,
                  borderRadius: 2,
                  background: "var(--surface-3)",
                  overflow: "hidden",
                }}
              >
                <div
                  style={{
                    height: "100%",
                    width: `${Math.max(2, fraction * 100)}%`,
                    background: tone,
                    transition: "width 0.5s linear",
                  }}
                />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
