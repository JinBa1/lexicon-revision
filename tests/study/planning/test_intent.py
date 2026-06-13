from __future__ import annotations

from typing import get_args

import pytest
from pydantic import ValidationError
from src.study.graph import _route_after_plan  # noqa: E402
from src.study.planning.intent import (
    DEFAULT_INTENT,
    DIRECT_RESPONSE_MESSAGES,
    INTENT_REGISTRY,
    IntentLiteral,
    IntentSpec,
)


def test_every_intent_has_a_registry_spec() -> None:
    for intent in get_args(IntentLiteral):
        assert intent in INTENT_REGISTRY


def test_direct_response_specs_reference_a_known_message() -> None:
    for spec in INTENT_REGISTRY.values():
        if spec.workflow == "direct_response":
            assert spec.response_kind in DIRECT_RESPONSE_MESSAGES


def test_content_retrieval_is_the_only_retrieval_workflow() -> None:
    retrieval = [i for i, s in INTENT_REGISTRY.items() if s.workflow == "retrieval"]
    assert retrieval == ["content_retrieval"]
    assert INTENT_REGISTRY["content_retrieval"].response_kind is None


def test_default_intent_is_content_retrieval() -> None:
    assert DEFAULT_INTENT == "content_retrieval"


def test_intent_spec_is_frozen() -> None:
    with pytest.raises(ValidationError):
        INTENT_REGISTRY["ambiguous"].workflow = "retrieval"  # type: ignore[misc]


def _state_with_intent(intent, *, in_taxonomy=True):
    from src.study.graph import StudyGraphState
    from src.study.models import StudyRequest
    from src.study.planning.models import QueryPlan

    # A future taxonomy intent (one not yet a member of IntentLiteral) can't pass
    # QueryPlan's Literal validation, so build the plan via model_construct to
    # simulate it. Routing must still key off workflow, not the intent value.
    if in_taxonomy:
        plan = QueryPlan(original_query="q", semantic_queries=["q"], intent=intent)
    else:
        plan = QueryPlan.model_construct(
            original_query="q", semantic_queries=["q"], intent=intent
        )
    return StudyGraphState(
        request=StudyRequest(query="q", scope={"collection": "c"}),
        request_id="r",
        plan=plan,
    )


def test_route_after_plan_uses_workflow():
    assert _route_after_plan(_state_with_intent("content_retrieval")) == "retrieve"
    assert _route_after_plan(_state_with_intent("ambiguous")) == "direct_response"


def test_registry_extension_routes_via_workflow_only(monkeypatch):
    # "edit the dict" recipe: a new direct_response intent routes correctly with
    # no graph change. Routing keys off workflow, not the intent value.
    import src.study.graph as graph_mod

    extended = dict(graph_mod.INTENT_REGISTRY)
    extended["research_synthesis"] = IntentSpec(
        workflow="direct_response", response_kind="out_of_scope"
    )
    monkeypatch.setattr(graph_mod, "INTENT_REGISTRY", extended)
    assert (
        _route_after_plan(_state_with_intent("research_synthesis", in_taxonomy=False))
        == "direct_response"
    )
