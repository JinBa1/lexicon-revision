import { useEffect } from "react";

type ResultLike = { chunk_id: string };

type UseResultListKeyboardNavArgs = {
  results: ResultLike[];
  selectedChunkId: string | null;
  onFocus: (chunkId: string) => void;
  onNavigate: (chunkId: string) => void;
  onCloseOverlay: () => void;
  isMobileOverlayOpen: boolean;
};

const BAIL_TAGS = new Set(["INPUT", "TEXTAREA", "SELECT"]);

function isEditableActive(): boolean {
  const el = document.activeElement;
  if (!el || !(el instanceof HTMLElement)) return false;
  if (BAIL_TAGS.has(el.tagName)) return true;
  if (el.isContentEditable || el.getAttribute("contenteditable") === "true") return true;
  return false;
}

export function useResultListKeyboardNav({
  results,
  selectedChunkId,
  onFocus,
  onNavigate,
  onCloseOverlay,
  isMobileOverlayOpen,
}: UseResultListKeyboardNavArgs): void {
  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (isEditableActive()) return;

      if (event.key === "ArrowDown" || event.key === "ArrowUp") {
        if (results.length === 0) return;
        const idx = selectedChunkId ? results.findIndex((r) => r.chunk_id === selectedChunkId) : -1;
        const start = idx >= 0 ? idx : 0;
        const next =
          event.key === "ArrowDown"
            ? Math.min(results.length - 1, start + 1)
            : Math.max(0, start - 1);
        const target = results[next];
        if (!target) return;
        event.preventDefault();
        onFocus(target.chunk_id);
        return;
      }

      if (event.key === "Enter") {
        if (selectedChunkId == null) return;
        event.preventDefault();
        onNavigate(selectedChunkId);
        return;
      }

      if (event.key === "Escape") {
        if (!isMobileOverlayOpen) return;
        event.preventDefault();
        onCloseOverlay();
        return;
      }
    }

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [results, selectedChunkId, onFocus, onNavigate, onCloseOverlay, isMobileOverlayOpen]);
}
