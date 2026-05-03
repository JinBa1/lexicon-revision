import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test, vi } from "vitest";

import { CollectionsGrid } from "@/components/collections/CollectionsGrid";
import {
  cambridgeAccessible,
  oxfordWrongAffiliation,
  publicCollection,
} from "../fixtures/collections";

describe("CollectionsGrid", () => {
  test("renders collection rows with the active scope marked", () => {
    render(
      <CollectionsGrid
        collections={[publicCollection, cambridgeAccessible, oxfordWrongAffiliation]}
        activeName={cambridgeAccessible.name}
        isSignedIn={true}
        onPickAccessible={() => {}}
        onPickLocked={() => {}}
      />,
    );

    expect(screen.getByRole("heading", { name: "Collections" })).toBeInTheDocument();
    expect(screen.queryByText("Click to change scope")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /MIT 6\.006 \(demo\)/ })).toBeInTheDocument();
    const activeButton = screen.getByRole("button", { name: /Cambridge CS Tripos\. Active scope/ });
    expect(activeButton).toHaveAttribute("aria-pressed", "true");
    expect(activeButton).toHaveClass("selectable-selected");
    expect(screen.getByRole("button", { name: /Oxford Mathematics\. Locked/ })).toBeInTheDocument();
  });

  test("renders a single-column row surface instead of a card grid", () => {
    render(
      <CollectionsGrid
        collections={[publicCollection, cambridgeAccessible, oxfordWrongAffiliation]}
        activeName={null}
        isSignedIn={true}
        onPickAccessible={() => {}}
        onPickLocked={() => {}}
      />,
    );

    const section = screen.getByRole("heading", { name: "Collections" }).closest("section");
    const rowSurface = section?.querySelector("[data-collection-rows]");

    expect(screen.getAllByRole("button")).toHaveLength(3);
    expect(section?.querySelector('[data-testid="collections-header-rule"]')).toHaveClass(
      "bg-rule-soft",
    );
    expect(rowSurface).toHaveClass("flex", "flex-col");
    expect(rowSurface?.className).not.toMatch(/grid-cols/);
  });

  test("routes accessible and locked picks to their callbacks", async () => {
    const onPickAccessible = vi.fn();
    const onPickLocked = vi.fn();

    render(
      <CollectionsGrid
        collections={[cambridgeAccessible, oxfordWrongAffiliation]}
        activeName={null}
        isSignedIn={true}
        onPickAccessible={onPickAccessible}
        onPickLocked={onPickLocked}
      />,
    );

    await userEvent.click(screen.getByRole("button", { name: /Cambridge CS Tripos/ }));
    await userEvent.click(screen.getByRole("button", { name: /Oxford Mathematics/ }));

    expect(onPickAccessible).toHaveBeenCalledWith(cambridgeAccessible);
    expect(onPickLocked).toHaveBeenCalledWith(oxfordWrongAffiliation);
  });
});
