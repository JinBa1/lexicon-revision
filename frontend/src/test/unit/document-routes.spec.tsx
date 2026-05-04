import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, test } from "vitest";

import { AboutRoute } from "@/routes/about";
import { PrivacyRoute } from "@/routes/privacy";

describe("document routes", () => {
  test("privacy notice uses meta strip and content panel", () => {
    render(
      <MemoryRouter>
        <PrivacyRoute />
      </MemoryRouter>,
    );

    expect(screen.getByRole("heading", { level: 1, name: "Privacy notice" })).toHaveClass(
      "font-display",
      "text-[38px]",
      "sm:text-[42px]",
    );
    expect(screen.queryByText("Launch scaffold")).not.toBeInTheDocument();
    expect(screen.getByText("Version")).toBeInTheDocument();
    expect(screen.getByText("Last updated")).toBeInTheDocument();
    expect(screen.getByTestId("doc-content-panel")).toHaveClass(
      "bg-paper-raised",
      "shadow-[0_12px_35px_rgba(0,0,0,0.04)]",
    );
    expect(screen.getByRole("link", { name: "Contact the ICO ↗" })).toHaveAttribute(
      "href",
      "https://ico.org.uk/make-a-complaint/data-protection-complaints/data-protection-complaints/",
    );
  });

  test("about page uses the same document shell", () => {
    render(
      <MemoryRouter>
        <AboutRoute />
      </MemoryRouter>,
    );

    expect(screen.getByRole("heading", { level: 1, name: "About" })).toHaveClass(
      "font-display",
      "text-[38px]",
      "sm:text-[42px]",
    );
    expect(screen.getByText("Version")).toBeInTheDocument();
    expect(screen.getByText("Last updated")).toBeInTheDocument();
    expect(screen.getByTestId("doc-content-panel")).toBeInTheDocument();
  });
});
