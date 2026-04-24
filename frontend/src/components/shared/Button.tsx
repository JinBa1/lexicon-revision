import { forwardRef, type ButtonHTMLAttributes } from "react";
import { cn } from "@/lib/cn";

type Variant = "primary" | "secondary" | "ghost" | "text";

export type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: Variant;
};

const base =
  "inline-flex items-center gap-2 rounded-md border font-display text-sm transition-colors " +
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-claret focus-visible:ring-offset-2 " +
  "focus-visible:ring-offset-paper disabled:cursor-not-allowed disabled:opacity-60";

const variants: Record<Variant, string> = {
  primary: "border-claret bg-claret text-paper-raised hover:bg-claret/90 px-4 py-2 font-semibold",
  secondary: "border-claret bg-transparent text-claret hover:bg-claret/10 px-4 py-2",
  ghost: "border-rule bg-transparent text-ink hover:bg-paper-raised px-3 py-1.5",
  text: "border-transparent bg-transparent text-claret hover:underline px-0 py-0",
};

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { className, variant = "primary", type = "button", ...rest },
  ref,
) {
  return (
    <button ref={ref} type={type} className={cn(base, variants[variant], className)} {...rest} />
  );
});
