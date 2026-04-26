import type { CodeBlock as CodeBlockType } from "@/lib/api/types";

export function CodeBlock({ block }: { block: CodeBlockType }) {
  return (
    <pre>
      <code>{block.code}</code>
    </pre>
  );
}
