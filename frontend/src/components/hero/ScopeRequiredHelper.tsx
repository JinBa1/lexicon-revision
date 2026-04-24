export function ScopeRequiredHelper({
  message = "Pick a collection below to enable search.",
}: {
  message?: string;
}) {
  return (
    <div aria-live="polite" className="font-ui text-[11px] uppercase tracking-wider text-ink-muted">
      {message}
    </div>
  );
}
