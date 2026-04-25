import { forwardRef } from "react";
import { cn } from "@/lib/cn";

export const CitationSup = forwardRef<
  HTMLButtonElement,
  {
    label: string;
    targetChunkId: string;
    onActivate: (chunkId: string) => void;
    className?: string;
  }
>(function CitationSup({ label, targetChunkId, onActivate, className }, ref) {
  return (
    <sup>
      <button
        ref={ref}
        type="button"
        onClick={() => onActivate(targetChunkId)}
        className={cn(
          "inline-block px-0.5 text-[0.7em] font-display text-claret underline decoration-rule-soft underline-offset-2 hover:decoration-claret",
          "focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-claret",
          className,
        )}
        aria-label={`Citation ${label}, view source ${targetChunkId}`}
      >
        {label}
      </button>
    </sup>
  );
});
