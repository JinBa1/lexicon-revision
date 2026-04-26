import { renderHook } from "@testing-library/react";
import { fireEvent } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { useResultListKeyboardNav } from "@/lib/hooks/useResultListKeyboardNav";

const RESULTS = [{ chunk_id: "a" }, { chunk_id: "b" }, { chunk_id: "c" }];

function setup(overrides: Partial<Parameters<typeof useResultListKeyboardNav>[0]> = {}) {
  const onFocus = vi.fn();
  const onNavigate = vi.fn();
  const onCloseOverlay = vi.fn();
  const args = {
    results: RESULTS,
    selectedChunkId: "a",
    onFocus,
    onNavigate,
    onCloseOverlay,
    isMobileOverlayOpen: false,
    ...overrides,
  };
  renderHook(() => useResultListKeyboardNav(args));
  return { onFocus, onNavigate, onCloseOverlay };
}

describe("useResultListKeyboardNav", () => {
  it("ArrowDown advances focus to next chunk_id", () => {
    const { onFocus } = setup();
    fireEvent.keyDown(window, { key: "ArrowDown" });
    expect(onFocus).toHaveBeenCalledWith("b");
  });

  it("ArrowUp at index 0 stays at index 0", () => {
    const { onFocus } = setup({ selectedChunkId: "a" });
    fireEvent.keyDown(window, { key: "ArrowUp" });
    expect(onFocus).toHaveBeenCalledWith("a");
  });

  it("ArrowDown at last index stays at last index", () => {
    const { onFocus } = setup({ selectedChunkId: "c" });
    fireEvent.keyDown(window, { key: "ArrowDown" });
    expect(onFocus).toHaveBeenCalledWith("c");
  });

  it("Enter with selection navigates", () => {
    const { onNavigate } = setup({ selectedChunkId: "b" });
    fireEvent.keyDown(window, { key: "Enter" });
    expect(onNavigate).toHaveBeenCalledWith("b");
  });

  it("Enter with null selection does nothing", () => {
    const { onNavigate } = setup({ selectedChunkId: null });
    fireEvent.keyDown(window, { key: "Enter" });
    expect(onNavigate).not.toHaveBeenCalled();
  });

  it("Esc closes overlay when mobile overlay is open", () => {
    const { onCloseOverlay } = setup({ isMobileOverlayOpen: true });
    fireEvent.keyDown(window, { key: "Escape" });
    expect(onCloseOverlay).toHaveBeenCalled();
  });

  it("Esc on desktop is no-op", () => {
    const { onCloseOverlay } = setup({ isMobileOverlayOpen: false });
    fireEvent.keyDown(window, { key: "Escape" });
    expect(onCloseOverlay).not.toHaveBeenCalled();
  });

  it("bails when activeElement is an input", () => {
    const input = document.createElement("input");
    document.body.appendChild(input);
    input.focus();
    const { onFocus } = setup();
    fireEvent.keyDown(window, { key: "ArrowDown" });
    expect(onFocus).not.toHaveBeenCalled();
    input.remove();
  });

  it("bails when activeElement is contenteditable", () => {
    const div = document.createElement("div");
    div.setAttribute("contenteditable", "true");
    div.tabIndex = 0;
    document.body.appendChild(div);
    div.focus();
    const { onFocus } = setup();
    fireEvent.keyDown(window, { key: "ArrowDown" });
    expect(onFocus).not.toHaveBeenCalled();
    div.remove();
  });
});
