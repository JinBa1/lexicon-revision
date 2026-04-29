from __future__ import annotations

from abc import ABC, abstractmethod

from src.chunking.mineru_segments import LogicalSegment
from src.chunking.models import ParsedQuestion


class BaseParser(ABC):
    @abstractmethod
    def parse(self, content_list_path: str) -> list[ParsedQuestion]:
        """Parse a MinerU content_list.json and return ParsedQuestion objects.

        For single-question-per-PDF formats (e.g. Cambridge), returns a
        single-element list. Multi-question formats return multiple elements.
        """

    @abstractmethod
    def parse_with_segments(
        self,
        content_list_path: str,
    ) -> tuple[list[ParsedQuestion], list[list[LogicalSegment]]]:
        """Parse questions and parser-preserved logical render segments."""
