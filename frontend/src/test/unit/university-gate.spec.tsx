import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, test, vi } from "vitest";

import { UniversityGate } from "@/components/auth/UniversityGate";
import type { SupportedUniversity } from "@/lib/api/types";
import { PROJECT_DISCUSSIONS_URL } from "@/lib/publicCopy";

const universities: SupportedUniversity[] = [
  {
    id: "cambridge",
    display_name: "University of Cambridge",
    email_domains: ["cam.ac.uk"],
  },
  {
    id: "mit",
    display_name: "MIT",
    email_domains: ["mit.edu"],
  },
];

describe("UniversityGate", () => {
  function renderUniversityGate(props: {
    initialSelected: string | null;
    onContinue: (universityId: string) => void;
  }) {
    return render(
      <MemoryRouter>
        <UniversityGate
          universities={universities}
          initialSelected={props.initialSelected}
          onContinue={props.onContinue}
        />
      </MemoryRouter>,
    );
  }

  test("disables continue until a university is selected", async () => {
    const user = userEvent.setup();
    const onContinue = vi.fn();

    renderUniversityGate({ initialSelected: null, onContinue });

    expect(screen.getByText("Sign-up · Step 1 of 2")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "← Back to home" })).toHaveAttribute("href", "/");
    expect(screen.getByRole("heading", { name: "Join your student community" })).toHaveClass(
      "text-[38px]",
      "font-bold",
    );
    expect(screen.getByText("Supported communities")).toBeInTheDocument();
    expect(screen.getByText("Choose a university to")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Continue →" })).toBeDisabled();
    expect(screen.getByRole("button", { name: /Create a community/i })).toBeDisabled();
    expect(screen.getByRole("link", { name: "✉ Contact support" })).toHaveAttribute(
      "href",
      PROJECT_DISCUSSIONS_URL,
    );
    expect(screen.getByRole("link", { name: "✉ Contact support" })).toHaveAttribute(
      "target",
      "_blank",
    );

    await user.click(screen.getByRole("button", { name: /MIT/i }));

    expect(
      screen.getByText(
        (_, node) => node?.textContent === "You'll verify with a mit.edu email next.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /MIT/i })).toHaveClass("bg-claret-active");

    await user.click(screen.getByRole("button", { name: "Continue →" }));

    expect(onContinue).toHaveBeenCalledWith("mit");
  });

  test("preselects the initial university", async () => {
    const user = userEvent.setup();
    const onContinue = vi.fn();

    renderUniversityGate({ initialSelected: "cambridge", onContinue });

    expect(screen.getByRole("button", { name: "Continue →" })).toBeEnabled();

    await user.click(screen.getByRole("button", { name: "Continue →" }));

    expect(onContinue).toHaveBeenCalledWith("cambridge");
  });
});
