import type { BlockIndicator } from "@/components/shared/render-blocks";

export function buildMetadataFallbackIndicators(
  metadata: Record<string, unknown>,
): BlockIndicator[] {
  const indicators: BlockIndicator[] = [];

  if (metadata.has_code === true) indicators.push({ kind: "code" });
  if (metadata.has_table === true) indicators.push({ kind: "table" });
  if (metadata.has_figure === true) indicators.push({ kind: "figure" });

  return indicators;
}
