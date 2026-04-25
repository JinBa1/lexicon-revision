import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test, vi } from "vitest";

import { NoAffiliationBanner } from "@/components/collections/NoAffiliationBanner";
import { WrongAffiliationModal } from "@/components/collections/WrongAffiliationModal";
import { oxfordWrongAffiliation } from "../fixtures/collections";

describe("NoAffiliationBanner", () => {
  test("announces that the signed-in account has no matching catalogue affiliation", () => {
    render(<NoAffiliationBanner />);

    expect(screen.getByRole("status")).toHaveTextContent(
      /no collection in our catalogue is currently tied to your email domain/i,
    );
    expect(screen.getByRole("status")).toHaveTextContent(/contact support/i);
  });
});

describe("WrongAffiliationModal", () => {
  test("renders nothing when there is no locked collection", () => {
    const { container } = render(<WrongAffiliationModal collection={null} onClose={() => {}} />);

    expect(container).toBeEmptyDOMElement();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  test("explains the mismatch with the backend lock reason when present", () => {
    render(<WrongAffiliationModal collection={oxfordWrongAffiliation} onClose={() => {}} />);

    expect(
      screen.getByRole("dialog", { name: "Oxford Mathematics access mismatch" }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/does not currently match the affiliation required/i),
    ).toBeInTheDocument();
    expect(screen.getByText("Unavailable to your account")).toBeInTheDocument();
  });

  test("falls back to generic lock messaging when the backend reason is absent", () => {
    render(
      <WrongAffiliationModal
        collection={{ ...oxfordWrongAffiliation, lock_reason: null }}
        onClose={() => {}}
      />,
    );

    expect(
      screen.getByText("Your signed-in account is not currently affiliated with this collection."),
    ).toBeInTheDocument();
  });

  test("moves focus to the in-place dialog when it appears", () => {
    render(<WrongAffiliationModal collection={oxfordWrongAffiliation} onClose={() => {}} />);

    expect(
      screen.getByRole("dialog", { name: "Oxford Mathematics access mismatch" }),
    ).toHaveFocus();
  });

  test("offers dismissal and a link back to supported universities", async () => {
    const onClose = vi.fn();

    render(<WrongAffiliationModal collection={oxfordWrongAffiliation} onClose={onClose} />);

    await userEvent.click(screen.getByRole("button", { name: "Dismiss" }));

    expect(onClose).toHaveBeenCalledOnce();
    expect(screen.getByRole("link", { name: "Supported universities" })).toHaveAttribute(
      "href",
      "#supported-universities",
    );
  });
});
