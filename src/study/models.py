from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, ConfigDict, Field
from src.metadata_schema.models import FilterCondition
from src.rendering.blocks import RenderBlock
from src.runtime.telemetry import TokenUsage
from src.search.pg_service import SearchExecutionTelemetry

if TYPE_CHECKING:
    from src.study.planning.models import PlanningMetadata

DraftAnswerStatus = Literal["ok", "partial", "insufficient_evidence"]
AnswerStatus = Literal[
    "ok",
    "partial",
    "insufficient_evidence",
    "generation_failed",
    "retrieval_failed",
    "no_corpus_answer",
]
RetrievalStatus = Literal[
    "ok", "empty", "filtered_empty", "error", "skipped", "low_relevance"
]
ErrorCategory = Literal[
    "provider_unreachable",
    "provider_timeout",
    "provider_error",
    "model_not_available",
    "schema_validation_failed",
    "citation_validation_cascade_failure",
    "context_build_failed",
    "context_pack_failed",
]


class StudyScope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    collection: str = Field(min_length=1)


class StudyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1)
    scope: StudyScope
    filters: list[FilterCondition] = Field(default_factory=list)
    top_k: int = Field(default=15, ge=1, le=50)


class StudyPattern(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str = Field(max_length=80)
    summary: str = Field(max_length=500)
    supporting_chunk_ids: list[str] = Field(min_length=1, max_length=5)


class CitedSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chunk_id: str = Field(min_length=1)
    why_cited: str = Field(max_length=400)


class StudyAnswerBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    overview: str = Field(max_length=1200)
    patterns: list[StudyPattern] = Field(default_factory=list, max_length=5)
    limitations: list[str] = Field(default_factory=list, max_length=5)


class StudyAnswerDraft(StudyAnswerBase):
    answer_status: DraftAnswerStatus
    cited_sources: list[CitedSource] = Field(default_factory=list, max_length=10)


class StudyAnswer(StudyAnswerBase):
    pass


class StudySource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chunk_id: str = Field(min_length=1)
    chunk_level: Literal["question", "sub_question"]
    parent_chunk_id: str | None
    sub_question_label: str | None
    score: float
    excerpt: str
    excerpt_blocks: list[RenderBlock] | None = None
    metadata: dict[str, Any]
    why_cited: str | None = Field(max_length=400)


class StudyResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["study_answer_v2"] = "study_answer_v2"
    request_id: str = Field(min_length=1)
    query: str = Field(min_length=1)
    scope: StudyScope
    answer_status: AnswerStatus
    answer: StudyAnswer
    sources: list[StudySource] = Field(default_factory=list)
    retrieval: "RetrievalMetadata"
    planning: PlanningMetadata
    generation: "GenerationMetadata"


class RetrievalMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: RetrievalStatus
    top_k: int = Field(ge=1)
    returned_result_count: int = Field(ge=0)
    context_budget_tokens: int = Field(ge=0)
    context_chunk_ids: list[str] = Field(default_factory=list)
    omitted_chunk_ids: list[str] = Field(default_factory=list)
    truncated_chunk_ids: list[str] = Field(default_factory=list)
    filters_applied: list[FilterCondition]
    rerank: bool
    # Reflection loop (all additive; default to the prior behaviour).
    reflection_graded: bool = False
    requery_attempted: bool = False
    # Count of chunks the grader ACCEPTED (kept), not the number evaluated.
    graded_chunk_count: int = Field(default=0, ge=0)
    grader_pruned_chunk_ids: list[str] = Field(default_factory=list)
    reflection_critique: str = ""
    reflection_reformulated_query: str = ""
    search_telemetry: SearchExecutionTelemetry | None = Field(
        default=None,
        exclude=True,
    )


class GenerationMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    prompt_version: str = Field(min_length=1)
    temperature: float
    attempt_count: int = Field(ge=0)
    citation_drops: int = Field(ge=0)
    error_category: ErrorCategory | None
    latency_ms: int = Field(ge=0)
    usage: TokenUsage | None = Field(default=None, exclude=True)


class RankedChunk(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chunk_id: str
    chunk_level: Literal["question", "sub_question"]
    parent_chunk_id: str | None
    text: str
    score: float
    metadata: dict[str, Any]


class PackedChunk(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chunk: RankedChunk
    text: str
    estimated_tokens: int
    truncated: bool = False


class PackingResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chunks: list[PackedChunk]
    omitted_chunk_ids: list[str]
    truncated_chunk_ids: list[str]
    status: Literal["ok", "context_pack_failed"] = "ok"


class ProviderCapabilities(BaseModel):
    model_config = ConfigDict(extra="forbid")

    json_schema_output: bool
    json_mode: bool
    max_context_tokens: int | None


class GenerationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    messages: list[dict[str, Any]]
    response_schema: dict[str, Any] | None
    temperature: float
    max_tokens: int | None
    timeout_seconds: float


class GenerationEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["token", "done"]
    text: str | None = None


class GenerationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    raw_content: str
    model: str
    provider: str
    finish_reason: str
    latency_ms: int = Field(ge=0)
    usage: TokenUsage | None = None


class ValidationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    draft: StudyAnswerDraft | None
    answer_status: AnswerStatus
    error_category: ErrorCategory | None
    citation_drops: int = Field(default=0, ge=0)
    limitations: list[str] = Field(default_factory=list)


from src.study.planning.models import PlanningMetadata  # noqa: E402

StudyRequest.model_rebuild()
StudyResponse.model_rebuild()
