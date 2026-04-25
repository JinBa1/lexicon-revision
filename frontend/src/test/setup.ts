import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

import { resetClerkTestState } from "./mocks/clerk-state";

vi.mock("@clerk/react", () => import("./mocks/clerk"));

afterEach(() => {
  cleanup();
  resetClerkTestState();
});
