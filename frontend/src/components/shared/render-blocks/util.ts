import type { RenderBlock } from "@/lib/api/types";

export function getReferencedMediaIds(blocks: RenderBlock[] | null): Set<string> {
  const out = new Set<string>();
  if (!blocks) return out;

  for (const block of blocks) {
    if (block.type === "image") out.add(block.media_id);
    if (block.type === "table" && block.media_id) out.add(block.media_id);
  }

  return out;
}

export type BlockIndicator = { kind: "figure" | "table" | "code" };

export function buildBlockIndicators(blocks: RenderBlock[]): BlockIndicator[] {
  const out: BlockIndicator[] = [];
  const seen = new Set<BlockIndicator["kind"]>();

  for (const block of blocks) {
    let kind: BlockIndicator["kind"] | null = null;
    if (block.type === "code") kind = "code";
    else if (block.type === "table") kind = "table";
    else if (block.type === "image") kind = "figure";

    if (kind && !seen.has(kind)) {
      seen.add(kind);
      out.push({ kind });
    }
  }

  return out;
}
