import { useId, useState } from "react";
import type { StudyRetrieval } from "@/lib/api/types";

export function RetrievalFooter({ retrieval }: { retrieval: StudyRetrieval }) {
  const diagnosticsId = useId();
  const [open, setOpen] = useState(false);
  return (
    <div className="mt-6 text-center">
      <button
        type="button"
        aria-controls={diagnosticsId}
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        className="font-display text-[11px] uppercase tracking-[0.1em] text-ink-muted hover:text-claret"
      >
        Based on {retrieval.returned_result_count} past-paper questions retrieved
      </button>
      {open ? (
        <div
          id={diagnosticsId}
          className="mx-auto mt-2 max-w-md rounded-sm border border-rule bg-paper-raised p-3 text-left font-mono text-[11px] text-ink-muted"
        >
          <div>top_k: {retrieval.top_k}</div>
          <div>rerank: {String(retrieval.rerank)}</div>
          <div>filters_applied: {JSON.stringify(retrieval.filters_applied)}</div>
        </div>
      ) : null}
    </div>
  );
}
