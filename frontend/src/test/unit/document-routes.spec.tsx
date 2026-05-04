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

    expect(screen.getByRole("heading", { level: 1, name: "Privacy notice" })).toBeInTheDocument();
    expect(screen.getByText("Version")).toBeInTheDocument();
    expect(screen.getByText("Last updated")).toBeInTheDocument();
    expect(screen.getByTestId("doc-content-panel")).toBeInTheDocument();
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

    expect(screen.getByRole("heading", { level: 1, name: "About" })).toBeInTheDocument();
    expect(screen.getByText("Version")).toBeInTheDocument();
    expect(screen.getByText("Last updated")).toBeInTheDocument();
    expect(screen.getByTestId("doc-content-panel")).toBeInTheDocument();
  });
});
