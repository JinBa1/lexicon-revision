from __future__ import annotations

from src.study.models import CitedSource, StudyAnswerDraft, StudyPattern
from src.study.validation import validate_citations


def test_validate_citations_keeps_valid_pattern_and_source() -> None:
    draft = StudyAnswerDraft(
        answer_status="ok",
        overview="In the retrieved questions, DP appears as recurrence design.",
        patterns=[
            StudyPattern(
                label="Recurrence design",
                summary="Questions ask for a recurrence.",
                supporting_chunk_ids=["a"],
            )
        ],
        cited_sources=[
            CitedSource(chunk_id="a", why_cited="It asks for a recurrence.")
        ],
        limitations=["Original limitation."],
    )

    result = validate_citations(draft, valid_chunk_ids={"a"})

    assert result.answer_status == "ok"
    assert result.error_category is None
    assert result.citation_drops == 0
    assert result.draft is not None
    assert result.draft.patterns[0].supporting_chunk_ids == ["a"]
    assert result.draft.limitations == ["Original limitation."]
    assert result.limitations == ["Original limitation."]


def test_validate_citations_downgrades_some_invalid_to_partial() -> None:
    draft = StudyAnswerDraft(
        answer_status="ok",
        overview="Overview",
        patterns=[
            StudyPattern(
                label="Mixed",
                summary="One valid and one invalid.",
                supporting_chunk_ids=["a", "missing"],
            )
        ],
        cited_sources=[
            CitedSource(chunk_id="missing-source", why_cited="Bad."),
            CitedSource(chunk_id="a", why_cited="Good."),
        ],
        limitations=["Original limitation."],
    )

    result = validate_citations(draft, valid_chunk_ids={"a"})

    assert result.answer_status == "partial"
    assert result.error_category is None
    assert result.citation_drops == 2
    assert result.draft is not None
    assert result.draft.patterns[0].supporting_chunk_ids == ["a"]
    assert [source.chunk_id for source in result.draft.cited_sources] == ["a"]
    assert result.draft.limitations == [
        "Original limitation.",
        "Some generated citations were removed because they did not match the "
        "retrieved sources.",
    ]
    assert result.limitations == result.draft.limitations


def test_validate_citations_normalizes_parenthesized_subpart_suffixes() -> None:
    draft = StudyAnswerDraft(
        answer_status="ok",
        overview="Overview",
        patterns=[
            StudyPattern(
                label="Set proofs",
                summary="Questions use set and number-theory proofs.",
                supporting_chunk_ids=[
                    "cam-2025-p2-q7(a)(i)",
                    "cam-2025-p2-q8(ii)",
                ],
            )
        ],
        cited_sources=[
            CitedSource(
                chunk_id="cam-2023-p2-q8-c(i)",
                why_cited="Relevant set-operation proof.",
            )
        ],
        limitations=[],
    )

    result = validate_citations(
        draft,
        valid_chunk_ids={
            "cam-2025-p2-q7",
            "cam-2025-p2-q8",
            "cam-2023-p2-q8-c",
        },
    )

    assert result.answer_status == "ok"
    assert result.citation_drops == 0
    assert result.draft is not None
    assert result.draft.patterns[0].supporting_chunk_ids == [
        "cam-2025-p2-q7",
        "cam-2025-p2-q8",
    ]
    assert [source.chunk_id for source in result.draft.cited_sources] == [
        "cam-2023-p2-q8-c"
    ]


def test_validate_citations_caps_partial_limitations() -> None:
    draft = StudyAnswerDraft(
        answer_status="ok",
        overview="Overview",
        patterns=[
            StudyPattern(
                label="Mixed",
                summary="One valid and one invalid.",
                supporting_chunk_ids=["a", "missing"],
            )
        ],
        cited_sources=[CitedSource(chunk_id="a", why_cited="Good.")],
        limitations=[
            "Limitation 1.",
            "Limitation 2.",
            "Limitation 3.",
            "Limitation 4.",
            "Limitation 5.",
        ],
    )

    result = validate_citations(draft, valid_chunk_ids={"a"})

    assert result.answer_status == "partial"
    assert result.draft is not None
    assert len(result.draft.limitations) == 5
    assert result.draft.limitations[-1].startswith("Some generated citations")
    assert result.limitations == result.draft.limitations


def test_validate_citations_all_invalid_cascade_fails() -> None:
    draft = StudyAnswerDraft(
        answer_status="ok",
        overview="Ungrounded overview",
        patterns=[
            StudyPattern(
                label="Bad",
                summary="Invalid support only.",
                supporting_chunk_ids=["missing"],
            )
        ],
        cited_sources=[CitedSource(chunk_id="also-missing", why_cited="Bad.")],
        limitations=["Original limitation."],
    )

    result = validate_citations(draft, valid_chunk_ids={"a"})

    assert result.answer_status == "generation_failed"
    assert result.error_category == "citation_validation_cascade_failure"
    assert result.draft is None
    assert result.citation_drops == 2
    assert result.limitations == [
        "Generated citations did not match retrieved sources.",
    ]
