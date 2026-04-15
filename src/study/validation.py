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
        valid_ids = [
            chunk_id
            for chunk_id in pattern.supporting_chunk_ids
            if chunk_id in valid_chunk_ids
        ]
        citation_drops += len(pattern.supporting_chunk_ids) - len(valid_ids)
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
        if source.chunk_id in valid_chunk_ids:
            kept_sources.append(source)
        else:
            citation_drops += 1

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
