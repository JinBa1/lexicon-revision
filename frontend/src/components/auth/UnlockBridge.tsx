import { Link } from "react-router-dom";

import type { CollectionListItem, SupportedUniversity } from "@/lib/api/types";

type UnlockBridgeProps = {
  collection: CollectionListItem;
  university: SupportedUniversity | null;
  returnTo: string;
};

const linkButtonBase =
  "inline-flex items-center justify-center gap-2 rounded-md border px-4 py-2 font-display text-sm " +
  "transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-claret " +
  "focus-visible:ring-offset-2 focus-visible:ring-offset-paper";
const primaryLinkButton = `${linkButtonBase} border-claret bg-claret font-semibold text-paper-raised hover:bg-claret/90`;
const secondaryLinkButton = `${linkButtonBase} border-claret bg-transparent text-claret hover:bg-claret/10`;

export function UnlockBridge({ collection, university, returnTo }: UnlockBridgeProps) {
  const communityName = collection.community?.display_name ?? "your institution";
  const emailDomain = university?.email_domains[0] ?? null;
  const signUpParams = new URLSearchParams({
    ...(collection.community ? { university: collection.community.id } : {}),
    returnTo,
  });
  const signInParams = new URLSearchParams({ returnTo });

  return (
    <main className="mx-auto max-w-2xl px-6 py-16 text-center">
      <h1 className="font-display text-3xl font-semibold leading-tight text-ink">
        {collection.display_name} is restricted to {communityName} members.
      </h1>
      {emailDomain ? (
        <p className="mt-3 font-body text-ink-muted">
          Use your <span className="font-mono text-ink">@{emailDomain}</span> email to sign up.
        </p>
      ) : null}
      <div className="mt-8 flex flex-col gap-3 sm:flex-row sm:justify-center">
        <Link to={`/sign-up?${signUpParams.toString()}`} className={primaryLinkButton}>
          {emailDomain
            ? `Sign up with ${emailDomain} email`
            : `Sign up with ${communityName} email`}
        </Link>
        <Link to={`/sign-in?${signInParams.toString()}`} className={secondaryLinkButton}>
          Sign in to an existing account
        </Link>
      </div>
      <div className="mt-6">
        <Link
          to="/sign-up"
          className="font-display text-[13px] italic text-ink-muted underline hover:text-claret"
        >
          Not at {communityName}? Browse supported universities -&gt;
        </Link>
      </div>
    </main>
  );
}
