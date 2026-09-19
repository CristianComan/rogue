import { describe, expect, it } from "vitest";
import { durationToSeconds, secondsToDuration } from "./duration";

describe("durationToSeconds", () => {
  it.each([
    ["PT0S", 0],
    ["PT5S", 5],
    ["PT1H30M", 5400],
    ["PT1H30M15S", 5415],
    ["P2D", 172800],
    ["P1DT2H", 93600],
    ["PT0.5S", 0.5],
  ])("parses %s as %d seconds", (duration, expected) => {
    expect(durationToSeconds(duration)).toBe(expected);
  });

  it("throws on an invalid duration string", () => {
    expect(() => durationToSeconds("not-a-duration")).toThrow();
  });
});

describe("secondsToDuration", () => {
  it.each([
    [0, "PT0S"],
    [5, "PT5S"],
    [5400, "PT1H30M"],
    [5415, "PT1H30M15S"],
    [172800, "P2D"],
    [93600, "P1DT2H"],
  ])("formats %d seconds as %s", (seconds, expected) => {
    expect(secondsToDuration(seconds)).toBe(expected);
  });

  it("round-trips through durationToSeconds for known Pydantic-style strings", () => {
    for (const duration of ["PT5S", "PT1H30M", "P2DT3H", "PT45S"]) {
      expect(secondsToDuration(durationToSeconds(duration))).toBe(duration);
    }
  });

  it("rejects negative durations", () => {
    expect(() => secondsToDuration(-1)).toThrow();
  });
});
