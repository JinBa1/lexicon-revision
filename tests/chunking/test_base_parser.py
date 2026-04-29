import pytest
from src.chunking.base_parser import BaseParser
from src.chunking.models import ParsedQuestion


def test_base_parser_cannot_be_instantiated():
    with pytest.raises(TypeError):
        BaseParser()


def test_base_parser_subclass_must_implement_parse(tmp_path):
    class IncompleteParser(BaseParser):
        pass

    with pytest.raises(TypeError):
        IncompleteParser()


def test_base_parser_subclass_must_implement_parse_with_segments(tmp_path):
    class ParseOnlyParser(BaseParser):
        def parse(self, content_list_path: str) -> list[ParsedQuestion]:
            return []

    with pytest.raises(TypeError):
        ParseOnlyParser()


def test_base_parser_subclass_with_full_contract_works(tmp_path):
    class DummyParser(BaseParser):
        def parse(self, content_list_path: str) -> list[ParsedQuestion]:
            return []

        def parse_with_segments(
            self,
            content_list_path: str,
        ) -> tuple[list[ParsedQuestion], list[list[object]]]:
            return [], []

    parser = DummyParser()
    result = parser.parse(str(tmp_path / "dummy_content_list.json"))
    assert result == []


def test_parser_registry_entries_support_parse_with_segments() -> None:
    from src.chunking.pipeline import PARSER_REGISTRY

    for parser_cls in PARSER_REGISTRY.values():
        parser = parser_cls()
        assert callable(parser.parse_with_segments)
