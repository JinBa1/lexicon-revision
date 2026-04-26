import type { ImageBlock as ImageBlockType, MediaRef } from "@/lib/api/types";

export function ImageBlock({
  block,
  media,
}: {
  block: ImageBlockType;
  media: MediaRef[] | undefined;
}) {
  const ref = media?.find((item) => item.media_id === block.media_id);

  return (
    <figure>
      {ref?.access_url ? (
        <img
          src={ref.access_url}
          alt="Question figure"
          className="mx-auto max-h-96 object-contain"
        />
      ) : (
        <div className="p-4 font-ui text-xs text-ink-muted">Image unavailable</div>
      )}
    </figure>
  );
}
