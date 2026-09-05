import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";

interface ScenarioTimeContextValue {
  scenarioTimeSeconds: number;
  isPlaying: boolean;
  playbackSpeed: number;
  seek: (seconds: number) => void;
  play: () => void;
  pause: () => void;
  setPlaybackSpeed: (speed: number) => void;
}

const ScenarioTimeContext = createContext<ScenarioTimeContextValue | null>(null);

/**
 * Owns the single scenario-time number and the *only* requestAnimationFrame
 * loop in this feature (CLAUDE.md rule 14: mission/RF state must be
 * computable from scenario time, independent of UI frame rate). The map,
 * timeline and spectrum strip all derive their display purely from
 * `scenarioTimeSeconds` via the pure domain/missionEvaluator functions —
 * none of them own timing state themselves.
 */
export function ScenarioTimeProvider({
  maxSeconds,
  children,
}: {
  maxSeconds: number;
  children: ReactNode;
}) {
  const [scenarioTimeSeconds, setScenarioTimeSeconds] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const [playbackSpeed, setPlaybackSpeed] = useState(1);
  const rafRef = useRef<number | null>(null);
  const lastFrameRef = useRef<number | null>(null);

  useEffect(() => {
    if (!isPlaying) {
      lastFrameRef.current = null;
      return;
    }

    function tick(now: number) {
      if (lastFrameRef.current !== null) {
        const deltaSeconds = ((now - lastFrameRef.current) / 1000) * playbackSpeed;
        setScenarioTimeSeconds((prev) => {
          const next = prev + deltaSeconds;
          return next >= maxSeconds ? 0 : next;
        });
      }
      lastFrameRef.current = now;
      rafRef.current = requestAnimationFrame(tick);
    }

    rafRef.current = requestAnimationFrame(tick);
    return () => {
      if (rafRef.current !== null) cancelAnimationFrame(rafRef.current);
    };
  }, [isPlaying, playbackSpeed, maxSeconds]);

  const seek = useCallback((seconds: number) => {
    setScenarioTimeSeconds(Math.max(0, seconds));
  }, []);

  const value: ScenarioTimeContextValue = {
    scenarioTimeSeconds,
    isPlaying,
    playbackSpeed,
    seek,
    play: () => setIsPlaying(true),
    pause: () => setIsPlaying(false),
    setPlaybackSpeed,
  };

  return <ScenarioTimeContext.Provider value={value}>{children}</ScenarioTimeContext.Provider>;
}

export function useScenarioTime(): ScenarioTimeContextValue {
  const context = useContext(ScenarioTimeContext);
  if (!context) throw new Error("useScenarioTime must be used within a ScenarioTimeProvider");
  return context;
}
