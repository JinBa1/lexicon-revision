import type { ReactNode } from "react";

export function ErrorState({
  title,
  detail,
  actions,
}: {
  title: string;
  detail?: string;
  actions?: ReactNode;
}) {
  return (
    <div
      role="alert"
      className="flex flex-col items-center gap-3 rounded-sm border border-rule bg-paper-raised px-6 py-10 text-center font-display"
    >
      <h3 className="text-lg font-semibold text-claret">{title}</h3>
      {detail ? <p className="max-w-prose text-sm text-ink-muted">{detail}</p> : null}
      {actions ? <div className="mt-2 flex gap-2">{actions}</div> : null}
    </div>
  );
}
