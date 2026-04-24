import type { ReactNode } from "react";

export function EmptyState({
  title,
  detail,
  actions,
}: {
  title: string;
  detail?: string;
  actions?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center gap-3 py-12 text-center font-display">
      <h3 className="text-lg font-semibold text-ink">{title}</h3>
      {detail ? <p className="max-w-prose text-sm text-ink-muted">{detail}</p> : null}
      {actions ? <div className="mt-2 flex gap-2">{actions}</div> : null}
    </div>
  );
}
