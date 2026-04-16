"""Generation provider adapters."""

from src.study.providers.base import (
    GenerationProvider,
    GeneratorHealth,
    ModelNotAvailableError,
    ProviderConnectionError,
    ProviderError,
    ProviderHTTPError,
    ProviderTimeoutError,
)
from src.study.providers.ollama import OllamaProvider

__all__ = [
    "GenerationProvider",
    "GeneratorHealth",
    "ModelNotAvailableError",
    "OllamaProvider",
    "ProviderConnectionError",
    "ProviderError",
    "ProviderHTTPError",
    "ProviderTimeoutError",
]
