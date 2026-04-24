import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test, vi } from "vitest";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";

import { EmptyQuestions } from "@/components/questions/EmptyQuestions";
import { InvalidFiltersState } from "@/components/questions/InvalidFiltersState";

function renderStates(ui: React.ReactNode, initialEntry: string) {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <LocationProbe />
      <Routes>
        <Route path="/c/:collection/questions" element={ui} />
        <Route path="*" element={<div />} />
      </Routes>
    </MemoryRouter>,
  );
}

function LocationProbe() {
  const location = useLocation();
  return (
    <div data-testid="location">
      {location.pathname}
      {location.search}
    </div>
  );
}

describe("question route state components", () => {
  test("clears every filter param while preserving other params", async () => {
    renderStates(
      <InvalidFiltersState collectionName="cam-cs-tripos" offendingField="paper" />,
      "/c/cam-cs-tripos/questions?q=trees&filter=year%3Agte%3A2020&filter=paper%3Aeq%3A5&focus=x",
    );

    expect(screen.getByRole("alert")).toHaveTextContent("Filters in this link aren't valid");
    expect(screen.getByRole("alert")).toHaveTextContent(
      'The filter "paper" is not available in cam-cs-tripos. Adjust or clear filters to continue.',
    );

    await userEvent.click(screen.getByRole("button", { name: "Clear filters" }));

    expect(screen.getByTestId("location")).toHaveTextContent(
      "/c/cam-cs-tripos/questions?q=trees&focus=x",
    );
  });

  test("secondary action returns to collection home", async () => {
    renderStates(
      <InvalidFiltersState collectionName="cam-cs-tripos" />,
      "/c/cam-cs-tripos/questions?filter=bad",
    );

    await userEvent.click(screen.getByRole("button", { name: "Back to collection" }));

    expect(screen.getByTestId("location")).toHaveTextContent("/c/cam-cs-tripos");
  });

  test("empty questions links to grounded answer and switches collection through callback", async () => {
    const onBroadenFilters = vi.fn();
    const onSwitchCollection = vi.fn();

    renderStates(
      <EmptyQuestions
        collectionName="cam-cs-tripos"
        collectionDisplay="Cambridge CS Tripos"
        query="dynamic arrays"
        filters={[{ field: "year", op: "gte", value: 2021 }]}
        onEditFilters={onBroadenFilters}
        onSwitchCollection={onSwitchCollection}
      />,
      "/c/cam-cs-tripos/questions?q=dynamic+arrays",
    );

    expect(
      screen.getByText("No past-paper questions match this query in Cambridge CS Tripos"),
    ).toBeInTheDocument();
    const answerCta = screen.getByRole("link", { name: "Try a grounded answer instead" });
    expect(answerCta).toHaveAttribute(
      "href",
      "/c/cam-cs-tripos/answer?q=dynamic+arrays&filter=year%3Agte%3A2021",
    );
    expect(answerCta.tagName).toBe("A");
    expect(answerCta.querySelector("button")).toBeNull();

    await userEvent.click(screen.getByRole("button", { name: "Broaden filters" }));
    await userEvent.click(screen.getByRole("button", { name: "Switch collection" }));

    expect(onBroadenFilters).toHaveBeenCalledOnce();
    expect(onSwitchCollection).toHaveBeenCalledOnce();
  });
});
