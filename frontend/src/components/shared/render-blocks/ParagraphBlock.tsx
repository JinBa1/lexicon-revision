import type { ParagraphBlock as ParagraphBlockType } from "@/lib/api/types";

import { InlineRuns } from "./InlineRuns";

export function ParagraphBlock({ block }: { block: ParagraphBlockType }) {
  return (
    <p>
      <InlineRuns runs={block.runs} />
    </p>
  );
}
