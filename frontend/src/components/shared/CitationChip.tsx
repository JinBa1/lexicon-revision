import { forwardRef } from "react";
import { cn } from "@/lib/cn";

export const CitationChip = forwardRef<
  HTMLButtonElement,
  {
    label: string;
    targetChunkId: string;
    onActivate: (chunkId: string) => void;
    className?: string;
  }
>(function CitationChip({ label, targetChunkId, onActivate, className }, ref) {
  return (
    <button
      ref={ref}
      type="button"
      onClick={() => onActivate(targetChunkId)}
      aria-label={`Jump to source ${label}`}
      className={cn(
        "mx-0.5 inline-flex items-center justify-center rounded-full border border-claret px-2 py-px",
        "bg-white font-ui text-[11px] font-bold text-claret transition-colors hover:bg-claret hover:text-white",
        "focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-claret focus-visible:ring-offset-1 focus-visible:ring-offset-paper",
        className,
      )}
    >
      {label}
    </button>
  );
});
