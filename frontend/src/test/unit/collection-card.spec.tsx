import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, test, vi } from "vitest";
import { CollectionCard } from "@/components/collections/CollectionCard";
import {
  cambridgeAccessible,
  cambridgeLocked,
  oxfordWrongAffiliation,
} from "../fixtures/collections";

function wrap(ui: React.ReactNode) {
  return <MemoryRouter>{ui}</MemoryRouter>;
}

describe("CollectionCard", () => {
  test("accessible row shows title and metadata", () => {
    render(
      wrap(
        <CollectionCard
          collection={cambridgeAccessible}
          isActive={false}
          isSignedIn={false}
          onPickAccessible={() => {}}
          onPickLocked={() => {}}
        />,
      ),
    );
    expect(screen.getByText("Cambridge CS Tripos")).toBeInTheDocument();
    expect(screen.getByText("Cambridge · 744 papers · 2018–25")).toBeInTheDocument();
    expect(screen.getByRole("button")).toHaveClass("flex-row");
  });

  test("active row exposes Active scope state accessibly", () => {
    render(
      wrap(
        <CollectionCard
          collection={cambridgeAccessible}
          isActive={true}
          isSignedIn={false}
          onPickAccessible={() => {}}
          onPickLocked={() => {}}
        />,
      ),
    );
    expect(screen.getByText(/Active scope/i)).toBeInTheDocument();
    const btn = screen.getByRole("button", { name: /Active scope/i });
    expect(btn).toHaveAttribute("aria-pressed", "true");
    expect(btn).toHaveClass("selectable-selected");
    expect(btn).not.toHaveClass("border-rule");
    expect(btn).not.toHaveClass("border-l-transparent");
    expect(btn).not.toHaveClass("bg-paper-raised");
    expect(btn).not.toHaveClass("bg-paper-lock");
  });

  test("locked anonymous click calls onPickLocked with signin reason", async () => {
    const onPickLocked = vi.fn();
    render(
      wrap(
        <CollectionCard
          collection={cambridgeLocked}
          isActive={false}
          isSignedIn={false}
          onPickAccessible={() => {}}
          onPickLocked={onPickLocked}
        />,
      ),
    );
    await userEvent.click(screen.getByRole("button"));
    expect(onPickLocked).toHaveBeenCalledWith(cambridgeLocked);
  });

  test("active locked row does not keep inactive lock styling tokens", () => {
    render(
      wrap(
        <CollectionCard
          collection={cambridgeLocked}
          isActive={true}
          isSignedIn={false}
          onPickAccessible={() => {}}
          onPickLocked={() => {}}
        />,
      ),
    );

    const btn = screen.getByRole("button", { name: /Active scope/i });
    expect(btn).toHaveClass("selectable-selected");
    expect(btn).not.toHaveClass("border-rule");
    expect(btn).not.toHaveClass("border-l-transparent");
    expect(btn).not.toHaveClass("bg-paper-raised");
    expect(btn).not.toHaveClass("bg-paper-lock");
    expect(btn).not.toHaveClass("opacity-90");
  });

  test("accessible click calls onPickAccessible", async () => {
    const onPickAccessible = vi.fn();
    render(
      wrap(
        <CollectionCard
          collection={cambridgeAccessible}
          isActive={false}
          isSignedIn={false}
          onPickAccessible={onPickAccessible}
          onPickLocked={() => {}}
        />,
      ),
    );
    await userEvent.click(screen.getByRole("button"));
    expect(onPickAccessible).toHaveBeenCalledWith(cambridgeAccessible);
  });

  test("locked row has accessible label spelling out lock reason", () => {
    render(
      wrap(
        <CollectionCard
          collection={oxfordWrongAffiliation}
          isActive={false}
          isSignedIn={true}
          onPickAccessible={() => {}}
          onPickLocked={() => {}}
        />,
      ),
    );
    const btn = screen.getByRole("button");
    expect(btn).toHaveAttribute(
      "aria-label",
      expect.stringContaining("Unavailable to your account"),
    );
    expect(screen.getByText("Unavailable to your account")).toBeInTheDocument();
    expect(screen.queryByText(/310 papers/)).toBeNull();
    expect(screen.queryByText(/2019–25/)).toBeNull();
    expect(screen.queryByText(/verified by email/i)).toBeNull();
  });
});
