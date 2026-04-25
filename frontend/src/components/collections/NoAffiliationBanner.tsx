export function NoAffiliationBanner() {
  return (
    <div
      role="status"
      className="mb-4 rounded-sm border border-rule bg-paper-raised px-4 py-3 font-display text-sm text-ink-muted"
    >
      Your account is signed in, but no collection in our catalogue is currently tied to your email
      domain. If that's wrong, contact support.
    </div>
  );
}
