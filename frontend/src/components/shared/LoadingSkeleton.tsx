import { cn } from "@/lib/cn";

export function LoadingSkeleton({
  variant = "row",
  count = 1,
  className,
}: {
  variant?: "row" | "card" | "prose";
  count?: number;
  className?: string;
}) {
  return (
    <div className={cn("space-y-2", className)} aria-busy="true" aria-live="polite">
      {Array.from({ length: count }).map((_, i) => (
        <div
          key={i}
          className={cn(
            "animate-pulse rounded-sm bg-rule/50",
            variant === "row" && "h-14 w-full",
            variant === "card" && "h-28 w-full",
            variant === "prose" && "h-4 w-full",
          )}
        />
      ))}
    </div>
  );
}
