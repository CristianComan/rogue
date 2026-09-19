import { act, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ScenarioTimeProvider, useScenarioTime } from "./scenarioTimeContext";

function Probe() {
  const { scenarioTimeSeconds, isPlaying, play, pause, seek } = useScenarioTime();
  return (
    <div>
      <span data-testid="time">{scenarioTimeSeconds.toFixed(2)}</span>
      <span data-testid="playing">{String(isPlaying)}</span>
      <button onClick={play}>play</button>
      <button onClick={pause}>pause</button>
      <button onClick={() => seek(5)}>seek5</button>
    </div>
  );
}

describe("ScenarioTimeProvider", () => {
  beforeEach(() => {
    vi.useFakeTimers({ toFake: ["requestAnimationFrame", "performance", "Date"] });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("seek sets the time directly without playing", () => {
    render(
      <ScenarioTimeProvider maxSeconds={100}>
        <Probe />
      </ScenarioTimeProvider>,
    );

    act(() => screen.getByText("seek5").click());

    expect(screen.getByTestId("time")).toHaveTextContent("5.00");
    expect(screen.getByTestId("playing")).toHaveTextContent("false");
  });

  it("play advances scenario time via requestAnimationFrame", () => {
    render(
      <ScenarioTimeProvider maxSeconds={100}>
        <Probe />
      </ScenarioTimeProvider>,
    );

    act(() => screen.getByText("play").click());
    expect(screen.getByTestId("playing")).toHaveTextContent("true");

    act(() => {
      vi.advanceTimersByTime(1000);
    });

    const time = Number(screen.getByTestId("time").textContent);
    expect(time).toBeGreaterThan(0);
  });

  it("wraps back to 0 after reaching maxSeconds", () => {
    render(
      <ScenarioTimeProvider maxSeconds={0.5}>
        <Probe />
      </ScenarioTimeProvider>,
    );

    act(() => screen.getByText("play").click());
    act(() => {
      vi.advanceTimersByTime(2000);
    });

    const time = Number(screen.getByTestId("time").textContent);
    expect(time).toBeLessThan(0.5);
  });

  it("pause flips isPlaying back to false", () => {
    render(
      <ScenarioTimeProvider maxSeconds={100}>
        <Probe />
      </ScenarioTimeProvider>,
    );

    act(() => screen.getByText("play").click());
    expect(screen.getByTestId("playing")).toHaveTextContent("true");

    act(() => screen.getByText("pause").click());
    expect(screen.getByTestId("playing")).toHaveTextContent("false");
  });
});
