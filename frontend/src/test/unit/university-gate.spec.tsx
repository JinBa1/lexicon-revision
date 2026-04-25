import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test, vi } from "vitest";

import { UniversityGate } from "@/components/auth/UniversityGate";
import type { SupportedUniversity } from "@/lib/api/types";

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
  test("disables continue until a university is selected", async () => {
    const user = userEvent.setup();
    const onContinue = vi.fn();

    render(
      <UniversityGate universities={universities} initialSelected={null} onContinue={onContinue} />,
    );

    expect(screen.getByRole("button", { name: "Continue" })).toBeDisabled();

    await user.click(screen.getByRole("button", { name: /MIT/i }));
    await user.click(screen.getByRole("button", { name: "Continue" }));

    expect(onContinue).toHaveBeenCalledWith("mit");
  });

  test("preselects the initial university", async () => {
    const user = userEvent.setup();
    const onContinue = vi.fn();

    render(
      <UniversityGate
        universities={universities}
        initialSelected="cambridge"
        onContinue={onContinue}
      />,
    );

    expect(screen.getByRole("button", { name: "Continue" })).toBeEnabled();

    await user.click(screen.getByRole("button", { name: "Continue" }));

    expect(onContinue).toHaveBeenCalledWith("cambridge");
  });
});
