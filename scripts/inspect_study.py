"""Inspect local study generation output without running FastAPI."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Allow direct execution via `python scripts/inspect_study.py ...`.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.inspect_search import create_real_search_service  # noqa: E402
from scripts.search_tooling import build_filters, truncate_text  # noqa: E402
from src.search.service import (  # noqa: E402
    DEFAULT_CHROMA_DIR,
    DEFAULT_COLLECTION,
    CollectionNotFoundError,
)
from src.study.config import load_study_settings  # noqa: E402
from src.study.models import (  # noqa: E402
    GenerationRequest,
    GenerationResult,
    ProviderCapabilities,
    StudyAnswerDraft,
    StudyRequest,
    StudyResponse,
    StudyScope,
)
from src.study.planning.models import QueryPlanDraft  # noqa: E402
from src.study.providers.base import GeneratorHealth  # noqa: E402
from src.study.providers.ollama import OllamaProvider  # noqa: E402
from src.study.service import StudyService  # noqa: E402


@dataclass
class _RecordedInteraction:
    request: GenerationRequest
    result: GenerationResult | None
    error: str | None
    kind: str  # "planner" | "generation"


def _classify_schema(schema: dict[str, object] | None) -> str:
    if not schema:
        return "generation"
    title = schema.get("title") if isinstance(schema, dict) else None
    if isinstance(title, str) and title == "QueryPlanDraft":
        return "planner"
    return "generation"


@dataclass
class RecordingProvider:
    """Decorator around a GenerationProvider that records each generate() call."""

    inner: Any
    interactions: list[_RecordedInteraction] = field(default_factory=list)

    @property
    def capabilities(self) -> ProviderCapabilities:
        return self.inner.capabilities

    async def generate(self, request: GenerationRequest) -> GenerationResult:
        kind = _classify_schema(request.response_schema)
        try:
            result = await self.inner.generate(request)
        except Exception as exc:
            self.interactions.append(
                _RecordedInteraction(
                    request=request, result=None, error=repr(exc), kind=kind
                )
            )
            raise
        self.interactions.append(
            _RecordedInteraction(request=request, result=result, error=None, kind=kind)
        )
        return result

    async def health(self) -> GeneratorHealth:
        return await self.inner.health()

    async def aclose(self) -> None:
        aclose = getattr(self.inner, "aclose", None)
        if aclose is not None:
            await aclose()


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments for the study inspection utility."""
    parser = argparse.ArgumentParser(
        description="Inspect local study generation output"
    )
    parser.add_argument("query", help="Study query text")
    parser.add_argument(
        "--chroma-dir",
        default=DEFAULT_CHROMA_DIR,
        help=f"ChromaDB storage directory (default: {DEFAULT_CHROMA_DIR})",
    )
    parser.add_argument(
        "--collection",
        default=DEFAULT_COLLECTION,
        help=f"ChromaDB collection name (default: {DEFAULT_COLLECTION})",
    )
    parser.add_argument(
        "--top-k",
        type=_positive_int,
        default=None,
        help="Retrieval top-k (default: StudySettings.context.retrieval_top_k_default)",
    )
    parser.add_argument("--year", type=int, help="Filter by year")
    parser.add_argument("--paper", type=int, help="Filter by paper number")
    parser.add_argument("--topic", help="Filter by topic")
    parser.add_argument("--question", type=int, help="Filter by question number")
    parser.add_argument("--marks-min", type=int, help="Minimum marks filter")
    parser.add_argument(
        "--has-code", action="store_true", help="Filter for chunks with code"
    )
    parser.add_argument(
        "--has-figure", action="store_true", help="Filter for chunks with figures"
    )
    parser.add_argument(
        "--has-table", action="store_true", help="Filter for chunks with tables"
    )
    parser.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="Output format",
    )
    parser.add_argument(
        "--show-prompt",
        action="store_true",
        help="Include rendered prompt in text output",
    )
    parser.add_argument(
        "--show-raw",
        action="store_true",
        help="Include raw LLM completions in text output",
    )
    parser.add_argument(
        "--show-context",
        action="store_true",
        help="Include packed context chunk previews in text output",
    )
    parser.add_argument(
        "--max-text-chars",
        type=_positive_int,
        default=500,
        help="Preview length for excerpts and raw output in text mode",
    )
    parser.add_argument(
        "--settings",
        type=Path,
        default=None,
        help="Optional path to an alternate study settings YAML directory",
    )
    return parser.parse_args()


def _positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a positive integer") from exc
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


async def _run_orchestration(
    service: StudyService,
    provider: RecordingProvider,
    request: StudyRequest,
) -> StudyResponse:
    try:
        return await service.orchestrate(request)
    finally:
        await provider.aclose()


def _parse_attempt_draft(
    raw_content: str, kind: str
) -> tuple[dict[str, Any] | None, str | None]:
    try:
        if kind == "planner":
            draft = QueryPlanDraft.model_validate_json(raw_content)
        else:
            draft = StudyAnswerDraft.model_validate_json(raw_content)
    except Exception as exc:
        return None, str(exc)
    return draft.model_dump(), None


def _attempt_payload(
    interaction: _RecordedInteraction, *, kind: str | None = None
) -> dict[str, Any]:
    result = interaction.result
    display_kind = kind or interaction.kind
    if result is None:
        return {
            "kind": display_kind,
            "latency_ms": None,
            "raw_content": None,
            "parsed_draft": None,
            "parse_error": None,
            "provider_error": interaction.error,
        }
    parsed_draft, parse_error = _parse_attempt_draft(
        result.raw_content, interaction.kind
    )
    return {
        "kind": display_kind,
        "latency_ms": result.latency_ms,
        "raw_content": result.raw_content,
        "parsed_draft": parsed_draft,
        "parse_error": parse_error,
        "provider_error": None,
    }


def _cited_chunk_ids_from_draft(draft: dict[str, Any] | None) -> list[str]:
    if not draft:
        return []
    seen: set[str] = set()
    ordered: list[str] = []
    for pattern in draft.get("patterns", []) or []:
        for chunk_id in pattern.get("supporting_chunk_ids", []) or []:
            if chunk_id not in seen:
                seen.add(chunk_id)
                ordered.append(chunk_id)
    for source in draft.get("cited_sources", []) or []:
        chunk_id = source.get("chunk_id")
        if isinstance(chunk_id, str) and chunk_id not in seen:
            seen.add(chunk_id)
            ordered.append(chunk_id)
    return ordered


def build_payload(
    *,
    query: str,
    collection: str,
    filters: dict[str, Any],
    top_k: int,
    response: StudyResponse,
    interactions: list[_RecordedInteraction],
    prompt_version: str,
) -> dict[str, Any]:
    """Assemble the stable machine-readable payload."""
    response_dump = response.model_dump()

    planner_interactions = [i for i in interactions if i.kind == "planner"]
    generation_interactions = [i for i in interactions if i.kind == "generation"]

    planner_attempts = [_attempt_payload(i) for i in planner_interactions]
    gen_attempts: list[dict[str, Any]] = []
    if generation_interactions:
        gen_attempts.append(
            _attempt_payload(generation_interactions[0], kind="primary")
        )
        for interaction in generation_interactions[1:]:
            gen_attempts.append(_attempt_payload(interaction, kind="repair"))

    prompt_messages: list[dict[str, Any]] = []
    if generation_interactions:
        prompt_messages = [
            dict(message) for message in generation_interactions[0].request.messages
        ]

    final_source_ids = [source["chunk_id"] for source in response_dump["sources"]]
    last_draft = gen_attempts[-1]["parsed_draft"] if gen_attempts else None
    draft_referenced_ids = _cited_chunk_ids_from_draft(last_draft)
    dropped_chunk_ids = [
        chunk_id
        for chunk_id in draft_referenced_ids
        if chunk_id not in final_source_ids
    ]

    retrieval = response_dump["retrieval"]
    generation = response_dump["generation"]
    planning = response_dump["planning"]
    planning["attempts"] = planner_attempts

    return {
        "query": query,
        "collection": collection,
        "filters": filters,
        "top_k": top_k,
        "retrieval": {
            "status": retrieval["status"],
            "returned_result_count": retrieval["returned_result_count"],
            "context_chunk_ids": retrieval["context_chunk_ids"],
            "omitted_chunk_ids": retrieval["omitted_chunk_ids"],
            "truncated_chunk_ids": retrieval["truncated_chunk_ids"],
        },
        "planning": planning,
        "prompt": {
            "version": prompt_version,
            "messages": prompt_messages,
        },
        "generation": {
            "provider": generation["provider"],
            "model": generation["model"],
            "temperature": generation["temperature"],
            "attempt_count": generation["attempt_count"],
            "attempts": gen_attempts,
            "error_category": generation["error_category"],
            "latency_ms": generation["latency_ms"],
        },
        "validation": {
            "answer_status": response_dump["answer_status"],
            "citation_drops": generation["citation_drops"],
            "dropped_chunk_ids": dropped_chunk_ids,
        },
        "answer": response_dump["answer"],
        "sources": response_dump["sources"],
        "response": response_dump,
    }


def render_json(payload: dict[str, Any]) -> str:
    """Render the inspect payload as stable JSON."""
    return json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True)


def render_text(
    payload: dict[str, Any],
    *,
    show_prompt: bool,
    show_raw: bool,
    show_context: bool,
    max_text_chars: int,
) -> str:
    """Render the inspect payload as readable text."""
    retrieval = payload["retrieval"]
    generation = payload["generation"]
    validation = payload["validation"]
    answer = payload["answer"]

    lines = [
        f"Query: {payload['query']}",
        f"Collection: {payload['collection']}",
        f"Filters: {_format_mapping(payload['filters'])}",
        f"Top-k: {payload['top_k']}",
        "",
        (
            f"Retrieval [{retrieval['status']}]: "
            f"returned={retrieval['returned_result_count']} "
            f"packed={len(retrieval['context_chunk_ids'])} "
            f"omitted={len(retrieval['omitted_chunk_ids'])} "
            f"truncated={len(retrieval['truncated_chunk_ids'])}"
        ),
    ]

    packed_ids = retrieval["context_chunk_ids"]
    if packed_ids:
        lines.append("  Packed:")
        for index, chunk_id in enumerate(packed_ids, start=1):
            lines.append(f"    {index}. {chunk_id}")
    if retrieval["omitted_chunk_ids"]:
        lines.append(f"  Omitted: {retrieval['omitted_chunk_ids']}")
    if retrieval["truncated_chunk_ids"]:
        lines.append(f"  Truncated: {retrieval['truncated_chunk_ids']}")

    planning = payload.get("planning")
    if planning:
        lines.append("")
        lines.append(
            f"Planning [{planning['status']} {planning['planner_version']}]: "
            f"queries={planning['semantic_queries']} "
            f"latency_ms={planning['latency_ms']}"
        )
        if planning.get("error_category"):
            lines.append(f"  error_category: {planning['error_category']}")
        for index, attempt in enumerate(planning.get("attempts", []), start=1):
            header = f"  Attempt {index} (planner): latency_ms={attempt['latency_ms']}"
            if attempt["provider_error"]:
                header = f"{header} provider_error={attempt['provider_error']}"
            if attempt["parse_error"]:
                header = f"{header} parse_error=yes"
            lines.append(header)
            if show_raw and attempt["raw_content"] is not None:
                preview = truncate_text(attempt["raw_content"], max_text_chars * 4)
                for content_line in preview.splitlines() or [""]:
                    lines.append(f"    {content_line}")
            if attempt["parse_error"]:
                lines.append(f"    parse_error: {attempt['parse_error']}")

    if show_context:
        lines.append("")
        lines.append("Context sources (excerpts):")
        for index, source in enumerate(payload["sources"], start=1):
            lines.append(
                f"  {index}. {source['chunk_id']} "
                f"score={source['score']:.4f} topic={source.get('topic')}"
            )
            lines.append(
                f"     excerpt: {truncate_text(source['excerpt'], max_text_chars)}"
            )

    if show_prompt:
        lines.append("")
        lines.append(f"Prompt [{payload['prompt']['version']}]:")
        for message in payload["prompt"]["messages"]:
            role = message.get("role", "?")
            content = message.get("content", "")
            lines.append(f"  [{role}]")
            for content_line in str(content).splitlines() or [""]:
                lines.append(f"    {content_line}")

    lines.append("")
    lines.append(
        f"Generation [{generation['provider']} {generation['model']} "
        f"T={generation['temperature']}]: "
        f"attempts={generation['attempt_count']} "
        f"latency_ms={generation['latency_ms']}"
    )
    if generation["error_category"]:
        lines.append(f"  error_category: {generation['error_category']}")
    for index, attempt in enumerate(generation["attempts"], start=1):
        header = (
            f"  Attempt {index} ({attempt['kind']}): latency_ms={attempt['latency_ms']}"
        )
        if attempt["provider_error"]:
            header = f"{header} provider_error={attempt['provider_error']}"
        if attempt["parse_error"]:
            header = f"{header} parse_error=yes"
        lines.append(header)
        if show_raw and attempt["raw_content"] is not None:
            preview = truncate_text(attempt["raw_content"], max_text_chars * 4)
            for content_line in preview.splitlines() or [""]:
                lines.append(f"    {content_line}")
        if attempt["parse_error"]:
            lines.append(f"    parse_error: {attempt['parse_error']}")

    lines.append("")
    lines.append(
        f"Answer [{validation['answer_status']}]: "
        f"citation_drops={validation['citation_drops']}"
    )
    if validation["dropped_chunk_ids"]:
        lines.append(f"  dropped_chunk_ids: {validation['dropped_chunk_ids']}")
    overview = answer.get("overview") or ""
    if overview:
        lines.append("  Overview:")
        for content_line in overview.splitlines() or [""]:
            lines.append(f"    {content_line}")
    patterns = answer.get("patterns") or []
    if patterns:
        lines.append("  Patterns:")
        for pattern in patterns:
            lines.append(f"    - label: {pattern.get('label')}")
            summary = pattern.get("summary") or ""
            lines.append(f"      summary: {truncate_text(summary, max_text_chars)}")
            lines.append(
                f"      supporting: {pattern.get('supporting_chunk_ids') or []}"
            )
    limitations = answer.get("limitations") or []
    if limitations:
        lines.append("  Limitations:")
        for limitation in limitations:
            lines.append(f"    - {limitation}")

    sources = payload["sources"]
    if sources:
        lines.append("  Sources:")
        for index, source in enumerate(sources, start=1):
            why = source.get("why_cited")
            header = (
                f"    {index}. {source['chunk_id']} "
                f"score={source['score']:.4f} topic={source.get('topic')}"
            )
            if why:
                header = f"{header} why={truncate_text(why, max_text_chars)}"
            lines.append(header)
            if show_context or not retrieval["context_chunk_ids"]:
                lines.append(
                    "       excerpt: "
                    f"{truncate_text(source['excerpt'], max_text_chars)}"
                )

    lines.append("")
    lines.append(
        f"Status: answer_status={validation['answer_status']} "
        f"retrieval_status={retrieval['status']} "
        f"error_category={generation['error_category'] or 'none'}"
    )

    return "\n".join(lines)


def _format_mapping(mapping: dict[str, Any]) -> str:
    if not mapping:
        return "none"
    return " ".join(f"{key}={value}" for key, value in mapping.items())


def main() -> None:
    """Run the local study inspection CLI."""
    args = parse_args()
    filters = build_filters(
        year=args.year,
        paper=args.paper,
        topic=args.topic,
        question=args.question,
        marks_min=args.marks_min,
        has_code=True if args.has_code else None,
        has_figure=True if args.has_figure else None,
        has_table=True if args.has_table else None,
    )

    try:
        settings = (
            load_study_settings(args.settings)
            if args.settings is not None
            else load_study_settings()
        )
        top_k = args.top_k or settings.context.retrieval_top_k_default

        search_service = create_real_search_service(args.chroma_dir, rerank=True)
        inner_provider = OllamaProvider(
            base_url=settings.generation.base_url,
            model=settings.generation.model,
            max_retries=settings.generation.max_provider_retries,
        )
        provider = RecordingProvider(inner=inner_provider)

        from src.study.planning.planner import LLMQueryPlanner
        from src.study.planning.retrieval import PlannedRetrievalService

        query_planner = LLMQueryPlanner(provider=provider, settings=settings.planning)
        planned_retrieval = PlannedRetrievalService(search_service=search_service)

        study_service = StudyService(
            query_planner=query_planner,
            planned_retrieval=planned_retrieval,
            provider=provider,
            settings=settings,
        )

        request = StudyRequest(
            query=args.query,
            scope=StudyScope(collection=args.collection),
            filters=filters or None,
            top_k=top_k,
        )
        response = asyncio.run(_run_orchestration(study_service, provider, request))
    except CollectionNotFoundError as exc:
        print(f"Collection '{exc.collection_name}' not found.", file=sys.stderr)
        print(
            "Use scripts/inspect_chroma.py --list-collections to inspect available "
            "collections.",
            file=sys.stderr,
        )
        raise SystemExit(1) from exc
    except (OSError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    payload = build_payload(
        query=args.query,
        collection=args.collection,
        filters=filters,
        top_k=top_k,
        response=response,
        interactions=provider.interactions,
        prompt_version=settings.prompt.version,
    )

    output = (
        render_json(payload)
        if args.format == "json"
        else render_text(
            payload,
            show_prompt=args.show_prompt,
            show_raw=args.show_raw,
            show_context=args.show_context,
            max_text_chars=args.max_text_chars,
        )
    )
    print(output)


if __name__ == "__main__":
    main()
