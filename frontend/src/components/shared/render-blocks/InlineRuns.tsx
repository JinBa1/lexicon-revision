import { Fragment } from "react";

import type { InlineRun } from "@/lib/api/types";

import { Math } from "./Math";

export function InlineRuns({ runs }: { runs: InlineRun[] }) {
  return (
    <>
      {runs.map((run, index) => {
        if (run.type === "text") {
          return <Fragment key={index}>{run.text}</Fragment>;
        }

        return <Math key={index} latex={run.latex} displayMode={false} />;
      })}
    </>
  );
}
