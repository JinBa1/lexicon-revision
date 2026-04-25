import { useEffect, useMemo, useRef } from "react";
import { Navigate, useParams, useSearchParams } from "react-router-dom";

import { UnlockBridge } from "@/components/auth/UnlockBridge";
import { ErrorState } from "@/components/shared/ErrorState";
import { LoadingSkeleton } from "@/components/shared/LoadingSkeleton";
import { useAppAuth } from "@/lib/auth/runtime";
import { useCollections } from "@/lib/hooks/useCollections";
import { useSupportedUniversities } from "@/lib/hooks/useSupportedUniversities";
import { buildCollectionHref } from "@/lib/url/scope";

export function UnlockRoute() {
  const { collection: collectionName = "" } = useParams<{ collection: string }>();
  const [searchParams] = useSearchParams();
  const { isSignedIn } = useAppAuth();
  const collections = useCollections();
  const universities = useSupportedUniversities();
  const {
    data: collectionData,
    isError: collectionsIsError,
    isFetching: collectionsIsFetching,
    isLoading: collectionsIsLoading,
    refetch: refetchCollections,
  } = collections;
  const returnTo = searchParams.get("returnTo") ?? buildCollectionHref(collectionName);
  const refetchedStaleCollection = useRef<string | null>(null);

  const collection = useMemo(
    () => collectionData?.find((item) => item.name === collectionName) ?? null,
    [collectionData, collectionName],
  );
  const university = useMemo(() => {
    if (!collection?.community || !universities.data) {
      return null;
    }

    return universities.data.find((item) => item.id === collection.community?.id) ?? null;
  }, [collection, universities.data]);
  const staleRequiresSigninCollection =
    isSignedIn && collection?.access_state === "locked_requires_signin" ? collection.name : null;

  useEffect(() => {
    if (
      !staleRequiresSigninCollection ||
      collectionsIsFetching ||
      refetchedStaleCollection.current === staleRequiresSigninCollection
    ) {
      return;
    }

    refetchedStaleCollection.current = staleRequiresSigninCollection;
    void refetchCollections();
  }, [collectionsIsFetching, refetchCollections, staleRequiresSigninCollection]);

  if (collectionsIsLoading || universities.isLoading) {
    return (
      <main className="mx-auto max-w-2xl px-6 py-16">
        <LoadingSkeleton variant="prose" count={6} />
      </main>
    );
  }

  if (collectionsIsError || !collection) {
    return (
      <main className="mx-auto max-w-2xl px-6 py-16">
        <ErrorState
          title="Collection not found"
          detail={`"${collectionName}" is not in the catalogue.`}
        />
      </main>
    );
  }

  if (isSignedIn && collection.access_state === "locked_wrong_affiliation") {
    const next = new URLSearchParams({
      explain: "wrong-affiliation",
      collection: collection.name,
    });
    return <Navigate to={`/?${next.toString()}`} replace />;
  }

  if (collection.access_state === "accessible") {
    return <Navigate to={returnTo} replace />;
  }

  if (staleRequiresSigninCollection) {
    return (
      <main className="mx-auto max-w-2xl px-6 py-16">
        <LoadingSkeleton variant="prose" count={6} />
      </main>
    );
  }

  return <UnlockBridge collection={collection} university={university} returnTo={returnTo} />;
}
