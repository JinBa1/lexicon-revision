import { render, screen } from "@testing-library/react";
import { describe, expect, test } from "vitest";

import { HeroStatusStrip } from "@/components/hero/HeroStatusStrip";
import { cambridgeAccessible } from "../fixtures/collections";

describe("HeroStatusStrip", () => {
  test("prompts users to choose a collection and links to the collections anchor", () => {
    render(<HeroStatusStrip activeCollection={null} />);

    expect(screen.getByText(/Choose a collection below to enable search\./i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "View collections ↓" })).toHaveAttribute(
      "href",
      "#collections",
    );
  });

  test("shows the active collection name when selected", () => {
    render(<HeroStatusStrip activeCollection={cambridgeAccessible} />);

    expect(screen.getByText("Currently searching in Cambridge CS Tripos.")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "View collections ↓" })).toBeNull();
  });

  test("landing-unified chrome keeps the choose-collection prompt even when selected", () => {
    render(<HeroStatusStrip activeCollection={cambridgeAccessible} chrome="landing-unified" />);

    expect(screen.getByText(/Choose a collection below to enable search\./i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "View collections ↓" })).toHaveAttribute(
      "href",
      "#collections",
    );
    expect(screen.queryByText("Currently searching in Cambridge CS Tripos.")).toBeNull();
  });
});
