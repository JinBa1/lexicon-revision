import type { ReactNode } from "react";
import { cn } from "@/lib/cn";

type ChipVariant = "default" | "ghost" | "active" | "meta";

export type ChipProps = {
  children: ReactNode;
  variant?: ChipVariant;
  onClick?: () => void;
  className?: string;
  "aria-haspopup"?: boolean;
  "aria-expanded"?: boolean;
  title?: string;
};

const base = "inline-flex items-center gap-1 rounded-sm border px-2.5 py-1 text-xs font-display";
const variants: Record<ChipVariant, string> = {
  default: "border-rule bg-paper-raised text-ink",
  ghost: "border-rule bg-transparent text-ink",
  active: "border-claret bg-claret-soft text-claret",
  meta: "border-rule-soft bg-paper text-ink-muted",
};

export function Chip({
  children,
  variant = "default",
  onClick,
  className,
  title,
  ...aria
}: ChipProps) {
  const shared = cn(base, variants[variant], className);
  if (onClick) {
    return (
      <button type="button" className={shared} onClick={onClick} title={title} {...aria}>
        {children}
      </button>
    );
  }
  return (
    <span className={shared} title={title}>
      {children}
    </span>
  );
}
