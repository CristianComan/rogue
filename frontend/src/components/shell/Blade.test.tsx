import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { Blade, BladeSection } from "./Blade";

describe("Blade", () => {
  it("renders the kicker, title and sub", () => {
    render(
      <Blade kicker="SDR Console" title="AG-01" sub="real · online" onClose={vi.fn()}>
        content
      </Blade>,
    );
    expect(screen.getByText("SDR Console")).toBeInTheDocument();
    expect(screen.getByText("AG-01")).toBeInTheDocument();
    expect(screen.getByText("real · online")).toBeInTheDocument();
  });

  it("calls onClose when the scrim is clicked", () => {
    const onClose = vi.fn();
    render(
      <Blade kicker="k" title="t" onClose={onClose}>
        content
      </Blade>,
    );
    fireEvent.click(screen.getByTestId("blade-scrim"));
    expect(onClose).toHaveBeenCalled();
  });

  it("does not call onClose when the panel body is clicked", () => {
    const onClose = vi.fn();
    render(
      <Blade kicker="k" title="t" onClose={onClose}>
        content
      </Blade>,
    );
    fireEvent.click(screen.getByText("content"));
    expect(onClose).not.toHaveBeenCalled();
  });

  it("calls onClose when the close button is clicked", () => {
    const onClose = vi.fn();
    render(
      <Blade kicker="k" title="t" onClose={onClose}>
        content
      </Blade>,
    );
    fireEvent.click(screen.getByRole("button", { name: /close/i }));
    expect(onClose).toHaveBeenCalled();
  });
});

describe("BladeSection", () => {
  it("renders a title and key/value rows", () => {
    render(<BladeSection title="Identity" rows={[{ k: "mode", v: "real" }]} />);
    expect(screen.getByText("Identity")).toBeInTheDocument();
    expect(screen.getByText("mode")).toBeInTheDocument();
    expect(screen.getByText("real")).toBeInTheDocument();
  });

  it("renders an optional note", () => {
    render(<BladeSection title="Identity" rows={[]} note="a note" />);
    expect(screen.getByText("a note")).toBeInTheDocument();
  });
});
