import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test, vi } from "vitest";

import { HelperExamples, type HelperExample } from "@/components/hero/HelperExamples";
import { ScopeRequiredHelper } from "@/components/hero/ScopeRequiredHelper";

describe("HelperExamples", () => {
  test("groups default examples by action", () => {
    render(<HelperExamples onPick={() => {}} />);

    expect(screen.getByText("Try")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "binary search" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "amortized analysis" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "graph flows" })).toBeInTheDocument();

    expect(screen.getByText("Or ask")).toBeInTheDocument();
    expect(
      screen.getByRole("button", {
        name: "How do past papers examine amortized analysis?",
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", {
        name: "Explain graph flows using past-paper examples.",
      }),
    ).toBeInTheDocument();
  });

  test("calls onPick with the selected example", async () => {
    const examples = [
      { label: "binary search", action: "questions" },
      { label: "Explain graph flows using past-paper examples.", action: "answer" },
    ] satisfies HelperExample[];
    const onPick = vi.fn();

    render(<HelperExamples examples={examples} onPick={onPick} />);

    await userEvent.click(
      screen.getByRole("button", {
        name: "Explain graph flows using past-paper examples.",
      }),
    );

    expect(onPick).toHaveBeenCalledWith(examples[1]);
  });

  test("omits empty action groups", () => {
    render(
      <HelperExamples
        examples={[{ label: "binary search", action: "questions" }]}
        onPick={() => {}}
      />,
    );

    expect(screen.getByText("Try")).toBeInTheDocument();
    expect(screen.queryByText("Or ask")).not.toBeInTheDocument();
  });

  test("landing-unified example pills use roman text and keep the examples label", () => {
    render(<HelperExamples chrome="landing-unified" onPick={() => {}} />);

    expect(screen.getByText("Try examples")).toHaveClass("uppercase");
    expect(screen.getByRole("button", { name: "binary search" })).not.toHaveClass("italic");
  });
});

describe("ScopeRequiredHelper", () => {
  test("renders the default polite message", () => {
    render(<ScopeRequiredHelper />);

    const status = screen.getByText("Pick a collection below to enable search.");

    expect(status).toHaveAttribute("aria-live", "polite");
  });

  test("renders a custom message", () => {
    render(<ScopeRequiredHelper message="Select a corpus before asking." />);

    expect(screen.getByText("Select a corpus before asking.")).toBeInTheDocument();
  });
});
