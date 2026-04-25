import { useNavigate, useParams } from "react-router-dom";

import { HeaderEcho } from "@/components/questions/HeaderEcho";
import { Button } from "@/components/shared/Button";
import { ChunkCard } from "@/components/shared/ChunkCard";
import { ErrorState } from "@/components/shared/ErrorState";
import { LoadingSkeleton } from "@/components/shared/LoadingSkeleton";
import { isApiError } from "@/lib/api/errors";
import { useChunk } from "@/lib/hooks/useChunk";
import { buildQuestionsHref } from "@/lib/url/scope";

export function SourceRoute() {
  const { collection: collectionName = "", chunkId = "" } = useParams<{
    collection: string;
    chunkId: string;
  }>();
  const navigate = useNavigate();
  const { data, isLoading, isError, error, refetch } = useChunk({
    collection: collectionName,
    chunkId,
  });
  const questionsHref = buildQuestionsHref({
    collection: collectionName,
    query: "",
    filters: [],
  });

  return (
    <>
      <HeaderEcho
        page="source"
        collectionName={collectionName}
        initialQuery=""
        initialFilters={[]}
      />
      <main className="mx-auto max-w-4xl px-6 py-10">
        {isLoading ? (
          <LoadingSkeleton variant="prose" count={8} />
        ) : isError && isApiError(error) && error.status === 404 ? (
          <ErrorState
            title="Source not found"
            detail={`"${chunkId}" is no longer in ${collectionName}.`}
            actions={<Button onClick={() => navigate(questionsHref)}>Back to questions</Button>}
          />
        ) : isError && isApiError(error) && error.status === 403 ? (
          <ErrorState
            title="Access denied"
            actions={<Button onClick={() => navigate("/")}>Back to home</Button>}
          />
        ) : isError ? (
          <ErrorState
            title="Couldn't load source"
            actions={
              <Button variant="primary" onClick={() => refetch()}>
                Retry
              </Button>
            }
          />
        ) : data ? (
          <ChunkCard
            mode="full"
            chunk={{
              chunk_id: data.chunk_id,
              chunk_level: data.chunk_level,
              parent_chunk_id: data.parent_chunk_id,
              sub_question_label: data.sub_question_label,
              text: data.text,
              metadata: data.metadata,
              media: data.media,
            }}
            parent={data.parent}
          />
        ) : null}
      </main>
    </>
  );
}
