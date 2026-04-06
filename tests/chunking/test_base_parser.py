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


def test_base_parser_subclass_with_parse_works(tmp_path):
    class DummyParser(BaseParser):
        def parse(self, content_list_path: str) -> list[ParsedQuestion]:
            return []

    parser = DummyParser()
    result = parser.parse(str(tmp_path / "dummy_content_list.json"))
    assert result == []
