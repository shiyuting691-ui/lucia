from abc import ABC, abstractmethod
from typing import Any, Dict, Optional


class LLMResponse:
    def __init__(
        self,
        success: bool,
        content: Optional[str] = None,
        json_data: Optional[dict] = None,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        error: Optional[str] = None,
        latency_ms: Optional[int] = None,
        token_usage: Optional[dict] = None,
    ):
        self.success = success
        self.content = content
        self.json_data = json_data
        self.provider = provider
        self.model = model
        self.error = error
        self.latency_ms = latency_ms
        self.token_usage = token_usage or {}

    def __repr__(self):
        return f"LLMResponse(success={self.success}, provider={self.provider}, error={self.error})"

    @property
    def text(self) -> str:
        """Backward-compatible alias used by older agents and dashboard code."""
        return self.content or ""


class BaseLLMProvider(ABC):
    provider_name: str = "base"

    @abstractmethod
    def is_configured(self) -> bool:
        pass

    @abstractmethod
    def health_check(self) -> dict:
        pass

    @abstractmethod
    def generate_text(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: int = 2000,
    ) -> LLMResponse:
        pass

    @abstractmethod
    def generate_json(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.1,
        max_tokens: int = 2000,
    ) -> LLMResponse:
        pass
