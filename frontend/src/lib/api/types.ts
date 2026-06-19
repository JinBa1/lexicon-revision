export type CollectionAccessState =
  | "accessible"
  | "locked_requires_signin"
  | "locked_wrong_affiliation";

export type CollectionCommunitySummary = {
  id: string;
  display_name: string;
};

export type CollectionYearRange = {
  start: number;
  end: number;
};

export type MetadataFieldType = "string" | "integer" | "boolean";
export type MetadataOperator = "eq" | "gte" | "lte";

export type MetadataField = {
  key: string;
  label: string;
  type: MetadataFieldType;
  operators: MetadataOperator[];
  exposed: boolean;
  source: string | null;
};

export type CollectionMetadataSchema = {
  version: number;
  fields: MetadataField[];
};

export type CollectionListItem = {
  name: string;
  display_name: string;
  community: CollectionCommunitySummary | null;
  paper_count: number;
  year_range: CollectionYearRange | null;
  metadata_schema: CollectionMetadataSchema | null;
  access_state: CollectionAccessState;
  lock_reason: string | null;
};

export type SupportedUniversity = {
  id: string;
  display_name: string;
  email_domains: string[];
};

export type MediaRef = {
  media_id: string;
  kind: "image" | "table";
  object_key: string | null;
  access_url: string | null;
  relation: "direct" | "inherited_shared" | "visible_from_child";
};

export type ChunkParentContext = {
  text: string;
  metadata: Record<string, unknown>;
  render_blocks: RenderBlock[] | null;
};

export type ChunkDetail = {
  chunk_id: string;
  chunk_level: "question" | "sub_question";
  parent_chunk_id: string | null;
  sub_question_label: string | null;
  text: string;
  metadata: Record<string, unknown>;
  media: MediaRef[];
  collection: string;
  parent: ChunkParentContext | null;
  render_blocks: RenderBlock[] | null;
};

export type FilterValue = string | number | boolean;

export type FilterCondition = {
  field: string;
  op: MetadataOperator;
  value: FilterValue;
};

export type TextRun = { type: "text"; text: string };
export type MathRun = { type: "math"; latex: string };
export type InlineRun = TextRun | MathRun;

export type ParagraphBlock = { type: "paragraph"; runs: InlineRun[] };
export type ListBlock = {
  type: "list";
  marker: "bullet" | "ordered" | "plain";
  items: InlineRun[][];
};
export type EquationBlock = { type: "equation"; latex: string };
export type CodeBlock = { type: "code"; code: string; language: string | null };
export type TableBlock = {
  type: "table";
  rows: string[][];
  media_id: string | null;
};
export type ImageBlock = { type: "image"; media_id: string };

export type RenderBlock =
  | ParagraphBlock
  | ListBlock
  | EquationBlock
  | CodeBlock
  | TableBlock
  | ImageBlock;

export type SearchResult = {
  chunk_id: string;
  chunk_level: "question" | "sub_question";
  parent_chunk_id: string | null;
  sub_question_label: string | null;
  text: string;
  score: number;
  metadata: Record<string, unknown>;
  media: MediaRef[];
  render_blocks: RenderBlock[] | null;
};

export type SearchResponse = {
  query: string;
  collection: string;
  results: SearchResult[];
  total: number;
};

export type SearchRequest = {
  query: string;
  collection: string;
  filters: FilterCondition[];
  limit: number;
  rerank: boolean;
};

export type StudyPattern = {
  label: string;
  summary: string;
  supporting_chunk_ids: string[];
};

export type StudySource = {
  chunk_id: string;
  chunk_level: "question" | "sub_question";
  parent_chunk_id: string | null;
  sub_question_label: string | null;
  score: number;
  excerpt: string;
  metadata: Record<string, unknown>;
  why_cited: string | null;
  excerpt_blocks: RenderBlock[] | null;
};

export type StudyAnswerStatus =
  | "ok"
  | "partial"
  | "insufficient_evidence"
  | "generation_failed"
  | "retrieval_failed"
  | "no_corpus_answer";

export type StudyRetrieval = {
  status: "ok" | "empty" | "filtered_empty" | "error" | "skipped";
  top_k: number;
  returned_result_count: number;
  context_budget_tokens: number;
  context_chunk_ids: string[];
  omitted_chunk_ids: string[];
  truncated_chunk_ids: string[];
  filters_applied: FilterCondition[];
  rerank: boolean;
};

export type StudyPlanning = {
  status: "ok" | "fallback";
  planner_version: string;
  original_query: string;
  semantic_queries: string[];
  intent: "content_retrieval" | "corpus_analytics" | "ambiguous" | "out_of_scope";
  generation_guidance?: string;
  error_category:
    | "provider_unreachable"
    | "provider_timeout"
    | "planning_deadline_exceeded"
    | "provider_error"
    | "model_not_available"
    | "schema_validation_failed"
    | "invalid_plan"
    | null;
  latency_ms: number;
};

export type StudyGeneration = {
  provider: string;
  model: string;
  prompt_version: string;
  temperature: number;
  attempt_count: number;
  citation_drops: number;
  error_category:
    | "provider_unreachable"
    | "provider_timeout"
    | "provider_error"
    | "model_not_available"
    | "schema_validation_failed"
    | "citation_validation_cascade_failure"
    | "context_build_failed"
    | "context_pack_failed"
    | null;
  latency_ms: number;
};

export type StudyResponse = {
  schema_version: "study_answer_v2";
  request_id: string;
  query: string;
  scope: { collection: string };
  answer_status: StudyAnswerStatus;
  answer: {
    overview: string;
    patterns: StudyPattern[];
    limitations: string[];
  };
  sources: StudySource[];
  retrieval: StudyRetrieval;
  planning: StudyPlanning;
  generation: StudyGeneration;
};

export type StudyRequest = {
  query: string;
  scope: { collection: string };
  filters: FilterCondition[];
  top_k: number;
};
