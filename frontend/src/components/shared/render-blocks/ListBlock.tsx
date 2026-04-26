import type { ListBlock as ListBlockType } from "@/lib/api/types";

import { InlineRuns } from "./InlineRuns";

export function ListBlock({ block }: { block: ListBlockType }) {
  if (block.marker === "ordered") {
    return (
      <ol>
        {block.items.map((item, index) => (
          <li key={index}>
            <InlineRuns runs={item} />
          </li>
        ))}
      </ol>
    );
  }

  if (block.marker === "bullet") {
    return (
      <ul>
        {block.items.map((item, index) => (
          <li key={index}>
            <InlineRuns runs={item} />
          </li>
        ))}
      </ul>
    );
  }

  return (
    <div>
      {block.items.map((item, index) => (
        <div key={index}>
          <InlineRuns runs={item} />
        </div>
      ))}
    </div>
  );
}
