import type { ImageBlock as ImageBlockType, MediaRef } from "@/lib/api/types";

export function ImageBlock({
  block,
  media,
}: {
  block: ImageBlockType;
  media: MediaRef[] | undefined;
}) {
  const imageMedia = media?.filter((item) => item.kind === "image") ?? [];
  const imageIndex = imageMedia.findIndex((item) => item.media_id === block.media_id);
  const ref = imageIndex >= 0 ? imageMedia[imageIndex] : undefined;
  const alt = imageIndex >= 0 ? `Question figure ${imageIndex + 1}` : "Question figure";

  return (
    <figure>
      {ref?.access_url ? (
        <img src={ref.access_url} alt={alt} className="mx-auto max-h-96 object-contain" />
      ) : (
        <div className="p-4 font-ui text-xs text-ink-muted">Image unavailable</div>
      )}
    </figure>
  );
}
