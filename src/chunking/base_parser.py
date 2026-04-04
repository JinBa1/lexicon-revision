from __future__ import annotations

from abc import ABC, abstractmethod

from src.chunking.models import ParsedQuestion


class BaseParser(ABC):
    @abstractmethod
    def parse(self, pdf_path: str) -> list[ParsedQuestion]:
        """Parse a PDF file and return a list of ParsedQuestion objects.

        For single-question-per-PDF formats (e.g. Cambridge), returns a
        single-element list. Multi-question formats return multiple elements.
        """
