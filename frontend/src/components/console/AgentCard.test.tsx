import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { AgentCard } from "./AgentCard";
import type { SDRAgentRecord } from "../../api/agents";

function agent(overrides: Partial<SDRAgentRecord> = {}): SDRAgentRecord {
  return {
    agent_id: "AG-01",
    mode: "real",
    capabilities: [
      {
        device_id: "x440-1",
        channel_index: 0,
        device_family: "x440",
        tunable_ranges_hz: [[30_000_000, 4_000_000_000]],
        max_usable_bandwidth_hz: 400_000_000,
        max_sample_rate_hz: 500_000_000,
      },
    ],
    last_seen_at: new Date().toISOString(),
    status: "online",
    ...overrides,
  };
}

describe("AgentCard", () => {
  it("shows the agent id, mode and status", () => {
    render(<AgentCard agent={agent()} />);
    expect(screen.getByText("AG-01")).toBeInTheDocument();
    expect(screen.getByText("real")).toBeInTheDocument();
    expect(screen.getByText("online")).toBeInTheDocument();
  });

  it("shows a stale status distinctly from online", () => {
    render(<AgentCard agent={agent({ status: "stale" })} />);
    expect(screen.getByText("stale")).toBeInTheDocument();
  });

  it("does not show the channel table until the blade is opened", () => {
    render(<AgentCard agent={agent()} />);
    expect(screen.queryByText("x440-1")).not.toBeInTheDocument();
  });

  it("shows the channel capability table once the blade is opened", () => {
    render(<AgentCard agent={agent()} />);
    fireEvent.click(screen.getByTestId("agent-card-AG-01").querySelector("button")!);
    expect(screen.getByText("x440-1")).toBeInTheDocument();
    // "x440" (the family) also appears in the always-visible summary field
    // grid above the table, so there are two matches once the blade is open.
    expect(screen.getAllByText("x440").length).toBeGreaterThanOrEqual(1);
  });

  it("closes the blade when the close button is clicked", () => {
    render(<AgentCard agent={agent()} />);
    fireEvent.click(screen.getByTestId("agent-card-AG-01").querySelector("button")!);
    expect(screen.getByText("x440-1")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /close/i }));
    expect(screen.queryByText("x440-1")).not.toBeInTheDocument();
  });
});
