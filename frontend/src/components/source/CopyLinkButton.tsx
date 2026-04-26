// Copying can fail in insecure contexts or browsers with restricted clipboard
// access, so the failure path exposes a selectable URL instead of failing silently.
import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/shared/Button";

type CopyState = "idle" | "copied" | "failed";

type CopyLinkButtonProps = {
  url: string;
};

export function CopyLinkButton({ url }: CopyLinkButtonProps) {
  const [state, setState] = useState<CopyState>("idle");
  const resetTimerRef = useRef<number | null>(null);

  useEffect(() => {
    return () => {
      if (resetTimerRef.current !== null) {
        window.clearTimeout(resetTimerRef.current);
      }
    };
  }, []);

  const clearResetTimer = () => {
    if (resetTimerRef.current !== null) {
      window.clearTimeout(resetTimerRef.current);
      resetTimerRef.current = null;
    }
  };

  const handleClick = async () => {
    clearResetTimer();

    try {
      await navigator.clipboard.writeText(url);
      setState("copied");
      resetTimerRef.current = window.setTimeout(() => {
        setState("idle");
        resetTimerRef.current = null;
      }, 2_000);
    } catch {
      setState("failed");
    }
  };

  const message =
    state === "copied" ? "Link copied ✓" : state === "failed" ? "Copy failed — select URL" : "";

  return (
    <div className="inline-flex flex-wrap items-center gap-2">
      <Button variant="secondary" onClick={handleClick}>
        Copy link
      </Button>
      <span role="status" aria-live="polite" className="text-[12px] text-ink-muted">
        {message}
      </span>
      {state === "failed" ? (
        <input
          readOnly
          aria-label="Shareable source URL"
          value={url}
          className="min-w-0 flex-1 rounded-sm border border-rule bg-paper px-2 py-1 text-[12px] text-ink"
          onFocus={(event) => event.currentTarget.select()}
        />
      ) : null}
    </div>
  );
}
