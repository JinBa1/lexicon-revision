import { describe, expect, it } from "vitest";

import {
  buildBlockIndicators,
  getReferencedMediaIds,
} from "@/components/shared/render-blocks/util";
import type { RenderBlock } from "@/lib/api/types";

describe("getReferencedMediaIds", () => {
  it("collects ids from image and table blocks", () => {
    const blocks: RenderBlock[] = [
      { type: "image", media_id: "image_1" },
      { type: "table", rows: [["x"]], media_id: "table_2" },
      { type: "paragraph", runs: [{ type: "text", text: "x" }] },
    ];

    expect(getReferencedMediaIds(blocks)).toEqual(new Set(["image_1", "table_2"]));
  });

  it("ignores tables with null media_id", () => {
    const blocks: RenderBlock[] = [{ type: "table", rows: [["x"]], media_id: null }];

    expect(getReferencedMediaIds(blocks)).toEqual(new Set());
  });

  it("returns empty for null blocks", () => {
    expect(getReferencedMediaIds(null)).toEqual(new Set());
  });
});

describe("buildBlockIndicators", () => {
  it("emits one indicator per heavy block", () => {
    const blocks: RenderBlock[] = [
      { type: "code", code: "x", language: null },
      { type: "table", rows: [], media_id: null },
      { type: "image", media_id: "image_1" },
      { type: "paragraph", runs: [] },
    ];

    expect(buildBlockIndicators(blocks)).toEqual([
      { kind: "code" },
      { kind: "table" },
      { kind: "figure" },
    ]);
  });
});
