import { forwardRef, type InputHTMLAttributes } from "react";

import { cn } from "@/lib/cn";

export type QueryInputProps = Omit<InputHTMLAttributes<HTMLInputElement>, "size"> & {
  size?: "lg" | "md";
};

export const QueryInput = forwardRef<HTMLInputElement, QueryInputProps>(function QueryInput(
  { size = "lg", className, ...rest },
  ref,
) {
  return (
    <div
      className={cn(
        "flex items-center gap-3 rounded-md border border-rule bg-white focus-within:ring-2 focus-within:ring-claret focus-within:ring-offset-2",
        size === "lg" ? "px-5 py-4" : "px-3 py-2",
      )}
    >
      <span aria-hidden className="text-ink-muted">
        ❖
      </span>
      <input
        ref={ref}
        type="text"
        className={cn(
          "w-full border-0 bg-transparent font-body italic text-ink outline-none placeholder:italic placeholder:text-ink-muted",
          size === "lg" ? "text-[17px]" : "text-sm",
          className,
        )}
        placeholder="Enter a topic or a question…"
        aria-label="Query"
        {...rest}
      />
    </div>
  );
});
