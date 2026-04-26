# Render Blocks

`render-blocks/` renders the structured presentation payload returned by the
backend for exam chunks. The backend keeps `chunks.text` as the indexing and
fallback payload; `render_blocks` is the frontend display payload.

## Contract

Frontend types live in `frontend/src/lib/api/types.ts` and mirror
`src/rendering/blocks.py`.

- `InlineRun`: `{ type: "text", text }` or `{ type: "math", latex }`.
- `RenderBlock`: `paragraph`, `list`, `equation`, `code`, `table`, or `image`.
- Search results and chunk details use `render_blocks: RenderBlock[] | null`.
- Study sources use `excerpt_blocks: RenderBlock[] | null`.
- The cross-stack sample fixture is
  `frontend/src/test/fixtures/render-blocks/sample.json`; backend and frontend
  tests use it to keep the schema aligned.

## Components

`RenderBlocks.tsx` is the public renderer. Import it through `index.ts`:

```tsx
import { RenderBlocks } from "@/components/shared/render-blocks";
```

It accepts:

- `blocks`: structured blocks, or `null` when the API has no presentation
  payload.
- `mode`: `"full"` for source/detail views, `"compact"` for result cards and
  study source cards.
- `fallbackText`: rendered when `blocks` is `null` or empty.
- `media`: media refs used by full-mode image blocks.
- `compactLines`: optional line clamp count for compact mode.
- `className` and `containerProps`: wrapper customization.

Per-block components are deliberately small:

- `ParagraphBlock`: renders paragraph inline runs.
- `ListBlock`: renders ordered, bullet, or plain lists.
- `EquationBlock`: renders a display math block.
- `CodeBlock`: renders preformatted code text. `language` is currently part of
  the API contract but not used for syntax highlighting.
- `TableBlock`: renders inline table rows from `rows`; `media_id` is kept for
  contract and media-reference tracking.
- `ImageBlock`: resolves `media_id` against `media` and renders the signed
  `access_url`, otherwise shows `Image unavailable`.

## Math And Inline Runs

`InlineRuns.tsx` renders text runs as plain React text and math runs through
`Math.tsx`. `Math.tsx` uses KaTeX with `throwOnError: false`, `trust: false`,
and `output: "htmlAndMathml"`. Inline math passes `displayMode={false}`;
equation blocks pass `displayMode={true}`.

KaTeX CSS is imported once from `frontend/src/main.tsx`. Renderer layout styles
live in `frontend/src/index.css` under `.question-prose`,
`.question-prose-compact`, and `.question-prose-clamp`.

## Modes And Fallbacks

Full mode renders every block in order. If no blocks are present, it renders
`fallbackText` in a paragraph. If neither blocks nor fallback text exist,
`RenderBlocks` returns `null`.

Compact mode renders only inline-friendly content: paragraphs, lists, and
equations. Code, table, and image blocks are summarized with chips from
`buildBlockIndicators()`. If structured blocks are missing or empty, compact
mode renders `fallbackText` and does not build block indicators.

`ChunkCard` adds one extra fallback path: when compact cards have no structured
blocks, it builds metadata-derived indicators with
`buildMetadataFallbackIndicators()`.

## Media Handling

Image blocks render through `ImageBlock` using the matching `MediaRef.media_id`.
Table blocks render from their inline `rows`; a table `media_id` is still
counted as referenced media.

`getReferencedMediaIds(blocks)` returns image media IDs and table media IDs.
`ChunkCard` uses it in full mode to avoid rendering the same media twice: media
already represented by an image or table block is excluded from the trailing
`MediaList`.

## Integration Points

- `ResultRow` passes search-result `render_blocks` into compact `ChunkCard`.
- `DetailPanel` and `SourceRoute` pass child and parent `render_blocks` into
  full `ChunkCard`.
- `SourcesGrid` renders `StudySource.excerpt_blocks` in compact mode with
  `source.excerpt` fallback.

Keep this README aligned with the current component behavior and the shared
sample fixture when changing the render-block schema.
