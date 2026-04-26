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

  for (const block of blocks) {
    if (block.type === "code") out.push({ kind: "code" });
    else if (block.type === "table") out.push({ kind: "table" });
    else if (block.type === "image") out.push({ kind: "figure" });
  }

  return out;
}
