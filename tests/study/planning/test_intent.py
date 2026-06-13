from __future__ import annotations

from typing import get_args

import pytest
from pydantic import ValidationError
from src.study.planning.intent import (
    DEFAULT_INTENT,
    DIRECT_RESPONSE_MESSAGES,
    INTENT_REGISTRY,
    IntentLiteral,
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
