import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, test, vi } from "vitest";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";

import { HeaderEcho } from "@/components/questions/HeaderEcho";
import { cambridgeAccessible, cambridgeLocked } from "../fixtures/collections";

const { mockUseCollections } = vi.hoisted(() => ({
  mockUseCollections: vi.fn(),
}));

vi.mock("@/lib/hooks/useCollections", () => ({
  useCollections: mockUseCollections,
}));

function renderHeader(initialEntry = "/c/cam-cs-tripos/questions?q=old") {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <Routes>
        <Route
          path="/c/:collection/questions"
          element={
            <HeaderEcho
              page="questions"
              collectionName="cam-cs-tripos"
              initialQuery="old"
              initialFilters={[]}
            />
          }
        />
        <Route path="*" element={<LocationProbe />} />
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

describe("HeaderEcho", () => {
  beforeEach(() => {
    mockUseCollections.mockReturnValue({
      data: [cambridgeAccessible],
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    });
  });

  test("opens the landing scope picker with page and current query", async () => {
    renderHeader();

    const input = screen.getByLabelText("Query");
    await userEvent.clear(input);
    await userEvent.type(input, "dynamic arrays");
    await userEvent.click(screen.getByRole("button", { name: "Cambridge CS Tripos ▾" }));

    expect(screen.getByTestId("location")).toHaveTextContent(
      "/?scopePicker=1&page=questions&q=dynamic+arrays",
    );
  });

  test("omits blank query when opening the landing scope picker", async () => {
    renderHeader();

    await userEvent.clear(screen.getByLabelText("Query"));
    await userEvent.click(screen.getByRole("button", { name: "Cambridge CS Tripos ▾" }));

    expect(screen.getByTestId("location")).toHaveTextContent("/?scopePicker=1&page=questions");
  });

  test("submits to answer route with current query and filters", async () => {
    renderHeader();

    const input = screen.getByLabelText("Query");
    await userEvent.clear(input);
    await userEvent.type(input, "graph cuts");
    await userEvent.click(screen.getByRole("button", { name: "+ Filters" }));
    await userEvent.type(screen.getByLabelText("Year from"), "2021");
    await userEvent.click(screen.getByRole("button", { name: "Done" }));
    await userEvent.click(screen.getByRole("button", { name: "Get answer with sources" }));

    expect(screen.getByTestId("location")).toHaveTextContent(
      "/c/cam-cs-tripos/answer?q=graph+cuts&filter=year%3Agte%3A2021",
    );
  });

  test("shows restricted copy when cached collection is not accessible", () => {
    mockUseCollections.mockReturnValue({
      data: [cambridgeLocked],
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    });

    renderHeader();

    expect(screen.getByText("Access to Cambridge CS Tripos is restricted.")).toBeInTheDocument();
  });
});
