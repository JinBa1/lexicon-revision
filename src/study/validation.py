from __future__ import annotations

from src.study.models import (
    CitedSource,
    StudyAnswerDraft,
    StudyPattern,
    ValidationResult,
)

PARTIAL_LIMITATION = (
    "Some generated citations were removed because they did not match the "
    "retrieved sources."
)
CASCADING_FAILURE_LIMITATION = "Generated citations did not match retrieved sources."


def validate_citations(
    draft: StudyAnswerDraft,
    *,
    valid_chunk_ids: set[str],
) -> ValidationResult:
    citation_drops = 0
    kept_patterns: list[StudyPattern] = []

    for pattern in draft.patterns:
        valid_ids: list[str] = []
        for chunk_id in pattern.supporting_chunk_ids:
            normalized_id = _normalize_chunk_id(chunk_id, valid_chunk_ids)
            if normalized_id is None:
                citation_drops += 1
            elif normalized_id not in valid_ids:
                valid_ids.append(normalized_id)
        if valid_ids:
            kept_patterns.append(
                StudyPattern(
                    label=pattern.label,
                    summary=pattern.summary,
                    supporting_chunk_ids=valid_ids,
                )
            )

    kept_sources: list[CitedSource] = []
    for source in draft.cited_sources:
        normalized_id = _normalize_chunk_id(source.chunk_id, valid_chunk_ids)
        if normalized_id is None:
            citation_drops += 1
        else:
            kept_sources.append(
                CitedSource(chunk_id=normalized_id, why_cited=source.why_cited)
            )

    if citation_drops and not kept_patterns and not kept_sources:
        return ValidationResult(
            draft=None,
            answer_status="generation_failed",
            error_category="citation_validation_cascade_failure",
            citation_drops=citation_drops,
            limitations=[CASCADING_FAILURE_LIMITATION],
        )

    answer_status = draft.answer_status
    limitations = list(draft.limitations)
    if citation_drops:
        answer_status = "partial"
        limitations = _append_limited_limitation(limitations, PARTIAL_LIMITATION)

    return ValidationResult(
        draft=StudyAnswerDraft(
            answer_status=answer_status,
            overview=draft.overview,
            patterns=kept_patterns,
            cited_sources=kept_sources,
            limitations=limitations,
        ),
        answer_status=answer_status,
        error_category=None,
        citation_drops=citation_drops,
        limitations=limitations,
    )


def _normalize_chunk_id(chunk_id: str, valid_chunk_ids: set[str]) -> str | None:
    if chunk_id in valid_chunk_ids:
        return chunk_id

    matches = [
        valid_id for valid_id in valid_chunk_ids if chunk_id.startswith(f"{valid_id}(")
    ]
    if len(matches) != 1:
        return None
    return matches[0]


def _append_limited_limitation(
    limitations: list[str],
    limitation: str,
    *,
    max_items: int = 5,
) -> list[str]:
    if limitation in limitations:
        return limitations[:max_items]
    if len(limitations) < max_items:
        return [*limitations, limitation]
    return [*limitations[: max_items - 1], limitation]
