import katex from "katex";
import { useLayoutEffect, useRef } from "react";

export function Math({ latex, displayMode }: { latex: string; displayMode: boolean }) {
  const ref = useRef<HTMLSpanElement>(null);

  useLayoutEffect(() => {
    if (!ref.current) return;

    try {
      katex.render(latex, ref.current, {
        displayMode,
        throwOnError: false,
        trust: false,
        output: "htmlAndMathml",
      });
    } catch (err) {
      if (import.meta.env.DEV) {
        console.warn("KaTeX render failed", { latex, err });
      }
    }
  }, [latex, displayMode]);

  return <span ref={ref} />;
}
