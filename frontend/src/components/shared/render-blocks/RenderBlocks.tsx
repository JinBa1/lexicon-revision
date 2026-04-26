import type { CSSProperties, HTMLAttributes } from "react";

import { Chip } from "@/components/shared/Chip";
import { cn } from "@/lib/cn";
import type { MediaRef, RenderBlock } from "@/lib/api/types";

import { CodeBlock } from "./CodeBlock";
import { EquationBlock } from "./EquationBlock";
import { ImageBlock } from "./ImageBlock";
import { InlineRuns } from "./InlineRuns";
import { ListBlock } from "./ListBlock";
import { Math } from "./Math";
import { ParagraphBlock } from "./ParagraphBlock";
import { TableBlock } from "./TableBlock";
import { buildBlockIndicators } from "./util";

type RenderBlocksProps = {
  blocks: RenderBlock[] | null;
  mode: "full" | "compact";
  fallbackText?: string;
  media?: MediaRef[];
  compactLines?: number;
  className?: string;
  containerProps?: HTMLAttributes<HTMLDivElement>;
};

const INDICATOR_LABEL = {
  code: "Contains code",
  table: "Contains table",
  figure: "Contains figure",
} satisfies Record<ReturnType<typeof buildBlockIndicators>[number]["kind"], string>;

export function RenderBlocks({
  blocks,
  mode,
  fallbackText,
  media,
  compactLines,
  className,
  containerProps,
}: RenderBlocksProps) {
  const hasBlocks = blocks !== null && blocks.length > 0;
  const { className: containerClassName, ...restContainerProps } = containerProps ?? {};

  if (!hasBlocks && !fallbackText) {
    return null;
  }

  if (mode === "full") {
    return (
      <div className={cn("question-prose", containerClassName, className)} {...restContainerProps}>
        {hasBlocks ? (
          blocks.map((block, index) => <FullBlock key={index} block={block} media={media} />)
        ) : (
          <p>{fallbackText}</p>
        )}
      </div>
    );
  }

  const inlineBlocks = hasBlocks
    ? blocks.filter(
        (block) => block.type === "paragraph" || block.type === "list" || block.type === "equation",
      )
    : [];
  const indicators = hasBlocks ? buildBlockIndicators(blocks) : [];
  const clampStyle: CSSProperties = compactLines ? { WebkitLineClamp: compactLines } : {};
  const showInlineContent = hasBlocks ? inlineBlocks.length > 0 : Boolean(fallbackText);

  return (
    <div
      className={cn("question-prose-compact", containerClassName, className)}
      {...restContainerProps}
    >
      {showInlineContent ? (
        <div className="question-prose-clamp" style={clampStyle}>
          {hasBlocks ? (
            inlineBlocks.map((block, index) => <CompactInline key={index} block={block} />)
          ) : (
            <span>{fallbackText}</span>
          )}
        </div>
      ) : null}
      {indicators.length > 0 ? (
        <div className="mt-1 flex flex-wrap gap-1">
          {indicators.map((indicator, index) => (
            <Chip key={index} variant="ghost">
              {INDICATOR_LABEL[indicator.kind]}
            </Chip>
          ))}
        </div>
      ) : null}
    </div>
  );
}

function FullBlock({ block, media }: { block: RenderBlock; media: MediaRef[] | undefined }) {
  switch (block.type) {
    case "paragraph":
      return <ParagraphBlock block={block} />;
    case "list":
      return <ListBlock block={block} />;
    case "equation":
      return <EquationBlock block={block} />;
    case "code":
      return <CodeBlock block={block} />;
    case "table":
      return <TableBlock block={block} />;
    case "image":
      return <ImageBlock block={block} media={media} />;
  }
}

function CompactInline({ block }: { block: RenderBlock }) {
  if (block.type === "paragraph") {
    return (
      <span>
        <InlineRuns runs={block.runs} />{" "}
      </span>
    );
  }

  if (block.type === "list") {
    const firstTwo = block.items.slice(0, 2);

    return (
      <span>
        {firstTwo.map((item, index) => (
          <span key={index}>
            <InlineRuns runs={item} />
            {index < firstTwo.length - 1 ? " · " : " "}
          </span>
        ))}
      </span>
    );
  }

  if (block.type === "equation") {
    return (
      <span>
        <Math latex={block.latex} displayMode={false} />{" "}
      </span>
    );
  }

  return null;
}
