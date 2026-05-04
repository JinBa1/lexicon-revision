import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, test, vi } from "vitest";

import { CollectionsGrid } from "@/components/collections/CollectionsGrid";
import {
  cambridgeAccessible,
  oxfordWrongAffiliation,
  publicCollection,
} from "../fixtures/collections";

describe("CollectionsGrid", () => {
  function renderCollectionsGrid(ui: React.ReactNode) {
    return render(<MemoryRouter>{ui}</MemoryRouter>);
  }

  test("renders collection rows with the active scope marked", () => {
    renderCollectionsGrid(
      <CollectionsGrid
        collections={[publicCollection, cambridgeAccessible, oxfordWrongAffiliation]}
        activeName={cambridgeAccessible.name}
        isSignedIn={true}
        onPickAccessible={() => {}}
        onPickLocked={() => {}}
      />,
    );

    expect(screen.getByRole("heading", { name: "Collections" })).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "Can't find your course? Suggest a collection->" }),
    ).toHaveAttribute("href", "/sign-up");
    expect(screen.queryByText("Click to change scope")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /MIT 6\.006 \(demo\)/ })).toBeInTheDocument();
    const activeButton = screen.getByRole("button", { name: /Cambridge CS Tripos\. Active scope/ });
    expect(activeButton).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: /Oxford Mathematics\. Locked/ })).toBeInTheDocument();
  });

  test("renders one row per collection", () => {
    renderCollectionsGrid(
      <CollectionsGrid
        collections={[publicCollection, cambridgeAccessible, oxfordWrongAffiliation]}
        activeName={null}
        isSignedIn={true}
        onPickAccessible={() => {}}
        onPickLocked={() => {}}
      />,
    );

    expect(screen.getAllByRole("button")).toHaveLength(3);
  });

  test("routes accessible and locked picks to their callbacks", async () => {
    const onPickAccessible = vi.fn();
    const onPickLocked = vi.fn();

    renderCollectionsGrid(
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
