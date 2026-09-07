import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { getRun } from "../api/runs";
import { startedAt, stoppedAt, type ScenarioRun } from "../domain/run";

interface RunTimeContextValue {
  run: ScenarioRun;
  /** Seconds since the run's `started` event, frozen once stopped. Never negative. */
  runElapsedSeconds: number;
  /** The same wall-clock reading runElapsedSeconds was derived from — consumers needing
   *  "now" (e.g. a lease countdown) should read this instead of calling Date.now()
   *  themselves, so every countdown on the page advances from one shared clock tick. */
  nowMs: number;
}

const RunTimeContext = createContext<RunTimeContextValue | null>(null);

const POLL_INTERVAL_MS = 2000;

/**
 * The Replay page's clock — deliberately not the same object as
 * state/scenarioTimeContext.tsx's authoring scrub (per the design note:
 * "the two pages share evaluator code, not state"). Elapsed run time comes
 * from real timestamps (the run's `started`/`stopped` events), advanced by
 * wall-clock rAF while RUNNING and frozen once stopped — never scrubbable.
 * Polls GET run on an interval to pick up new events/leases/status, since
 * there is no push/WebSocket channel from the control plane today.
 */
export function RunTimeProvider({
  scenarioId,
  planId,
  runId,
  children,
}: {
  scenarioId: string;
  planId: string;
  runId: string;
  children: ReactNode;
}) {
  const [run, setRun] = useState<ScenarioRun | null>(null);
  const [now, setNow] = useState(() => Date.now());
  const rafRef = useRef<number | null>(null);

  useEffect(() => {
    let cancelled = false;
    function poll() {
      getRun(scenarioId, planId, runId)
        .then((r) => {
          if (!cancelled) setRun(r);
        })
        .catch(() => {
          // Transient fetch failures leave the last-known run displayed
          // rather than blanking the page; RunHeader/WatchdogFeed simply
          // show stale-but-real data until the next successful poll.
        });
    }
    poll();
    const interval = setInterval(poll, POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [scenarioId, planId, runId]);

  const isRunning = run?.status === "running";

  useEffect(() => {
    if (!isRunning) return;
    function tick() {
      setNow(Date.now());
      rafRef.current = requestAnimationFrame(tick);
    }
    rafRef.current = requestAnimationFrame(tick);
    return () => {
      if (rafRef.current !== null) cancelAnimationFrame(rafRef.current);
    };
  }, [isRunning]);

  if (!run) return null;

  const started = startedAt(run);
  const stopped = stoppedAt(run);
  const endMs = stopped ? new Date(stopped).getTime() : now;
  const runElapsedSeconds = started ? Math.max(0, (endMs - new Date(started).getTime()) / 1000) : 0;

  return (
    <RunTimeContext.Provider value={{ run, runElapsedSeconds, nowMs: now }}>
      {children}
    </RunTimeContext.Provider>
  );
}

export function useRunTime(): RunTimeContextValue {
  const context = useContext(RunTimeContext);
  if (!context) throw new Error("useRunTime must be used within a RunTimeProvider");
  return context;
}
