import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test, vi } from "vitest";

import { PatternsList } from "@/components/answer/PatternsList";
import { CitationChip } from "@/components/shared/CitationChip";
import type { StudyPattern } from "@/lib/api/types";

const patterns: StudyPattern[] = [
  {
    label: "Accounting method",
    summary: "Charge k units per push.",
    supporting_chunk_ids: ["cam-2022-p5-q3", "cam-2021-p5-q3"],
  },
];

describe("pattern citations", () => {
  test("renders citation as an accessible numbered chip", () => {
    render(<CitationChip label="1" targetChunkId="source-1" onActivate={() => {}} />);

    const chip = screen.getByRole("button", { name: /jump to source 1/i });
    expect(chip).toHaveTextContent("1");
  });

  test("renders one citation chip per supporting_chunk_id mapped by position", () => {
    const chunkIdToPosition = new Map([
      ["cam-2022-p5-q3", 1],
      ["cam-2021-p5-q3", 2],
    ]);
    render(
      <PatternsList
        patterns={patterns}
        chunkIdToPosition={chunkIdToPosition}
        onCitationActivate={() => {}}
      />,
    );
    expect(screen.getAllByRole("button")).toHaveLength(2);
    expect(screen.getByRole("button", { name: /jump to source 1/i })).toHaveTextContent("1");
    expect(screen.getByRole("button", { name: /jump to source 2/i })).toHaveTextContent("2");
  });

  test("skips citation chips whose chunk_id is not in sources", () => {
    const chunkIdToPosition = new Map([["cam-2022-p5-q3", 1]]);
    render(
      <PatternsList
        patterns={patterns}
        chunkIdToPosition={chunkIdToPosition}
        onCitationActivate={() => {}}
      />,
    );
    expect(screen.getAllByRole("button")).toHaveLength(1);
  });

  test("click fires onCitationActivate with chunk_id", async () => {
    const chunkIdToPosition = new Map([
      ["cam-2022-p5-q3", 1],
      ["cam-2021-p5-q3", 2],
    ]);
    const onActivate = vi.fn();
    render(
      <PatternsList
        patterns={patterns}
        chunkIdToPosition={chunkIdToPosition}
        onCitationActivate={onActivate}
      />,
    );
    await userEvent.click(screen.getByRole("button", { name: /jump to source 2/i }));
    expect(onActivate).toHaveBeenCalledWith("cam-2021-p5-q3");
  });
});
