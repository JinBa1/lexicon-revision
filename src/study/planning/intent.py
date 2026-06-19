from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

IntentLiteral = Literal[
    "content_retrieval",
    "corpus_analytics",
    "ambiguous",
    "out_of_scope",
]
IntentWorkflow = Literal["retrieval", "direct_response"]

DEFAULT_INTENT: IntentLiteral = "content_retrieval"


class IntentSpec(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    workflow: IntentWorkflow
    response_kind: str | None = None


INTENT_REGISTRY: dict[IntentLiteral, IntentSpec] = {
    "content_retrieval": IntentSpec(workflow="retrieval"),
    "corpus_analytics": IntentSpec(
        workflow="direct_response", response_kind="unsupported_analytics"
    ),
    "ambiguous": IntentSpec(
        workflow="direct_response", response_kind="needs_refinement"
    ),
    "out_of_scope": IntentSpec(
        workflow="direct_response", response_kind="out_of_scope"
    ),
}

# Short static student-facing copy for each direct-response intent. Keyed by
# IntentSpec.response_kind. LLM-authored tailored suggestions are a later upgrade.
DIRECT_RESPONSE_MESSAGES: dict[str, str] = {
    "unsupported_analytics": (
        "I can't compute corpus-wide statistics yet — counts, frequencies, or "
        "trends across papers. I can find and explain specific past questions; "
        "try naming a topic, paper, or year."
    ),
    "needs_refinement": (
        "Your question is a bit broad to answer from past papers. Try naming a "
        "specific topic, paper, or year — or browse the question bank to see "
        "what's covered."
    ),
    "out_of_scope": (
        "That looks outside this past-paper collection, so I can't answer it "
        "from the corpus. Try a topic, concept, or question from the papers "
        "instead."
    ),
}

# Extension recipe: to add a goal, add a value to IntentLiteral, one
# INTENT_REGISTRY row, a DIRECT_RESPONSE_MESSAGES entry if direct_response, and a
# planner-prompt example. The graph routes on workflow, so topology is unchanged.
# To make a now-unsupported goal servable later, change its row's workflow.
