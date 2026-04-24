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
  test("renders collection cards with the active scope marked", () => {
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
    expect(screen.getByText("Click to change scope")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /MIT 6\.006 \(demo\)/ })).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /Cambridge CS Tripos\. Active scope/ }),
    ).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: /Oxford Mathematics\. Locked/ })).toBeInTheDocument();
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
