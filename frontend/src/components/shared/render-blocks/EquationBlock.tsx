import type { EquationBlock as EquationBlockType } from "@/lib/api/types";

import { Math } from "./Math";

export function EquationBlock({ block }: { block: EquationBlockType }) {
  return <Math latex={block.latex} displayMode />;
}
