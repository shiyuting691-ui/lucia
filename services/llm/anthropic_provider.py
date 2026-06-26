"""
Anthropic Claude Provider

403（地区限制）时返回 provider_unavailable，不抛出异常。
"""
import os
import time
import logging

from .base import BaseLLMProvider, LLMResponse
from .openai_compatible_provider import _extract_json

logger = logging.getLogger(__name__)


class AnthropicProvider(BaseLLMProvider):
    provider_name = "claude"

    def __init__(self):
        self._api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        self._model   = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")

    def is_configured(self) -> bool:
        return bool(self._api_key)

    def health_check(self) -> dict:
        if not self.is_configured():
            return {"status": "not_configured", "available": False, "provider": "claude"}
        try:
            resp = self.generate_text("说'ok'", max_tokens=10)
            if resp.success:
                return {"status": "success", "available": True,
                        "provider": "claude", "model": self._model}
            error_type = "forbidden" if "403" in (resp.error or "") else "failed"
            return {"status": error_type, "available": False,
                    "provider": "claude", "error": resp.error}
        except Exception as e:
            return {"status": "failed", "available": False,
                    "provider": "claude", "error": str(e)}

    def generate_text(self, prompt: str, system_prompt=None,
                      temperature: float = 0.2, max_tokens: int = 2000) -> LLMResponse:
        if not self.is_configured():
            return LLMResponse(success=False, provider="claude",
                               error="provider_not_configured")
        t0 = time.time()
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=self._api_key)
            kwargs = dict(
                model=self._model,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
            if system_prompt:
                kwargs["system"] = system_prompt

            msg     = client.messages.create(**kwargs)
            latency = int((time.time() - t0) * 1000)
            content = msg.content[0].text
            usage   = msg.usage
            logger.info(f"[claude] generate_text OK latency={latency}ms")
            return LLMResponse(
                success=True, content=content, provider="claude",
                model=self._model, latency_ms=latency,
                token_usage={"prompt": usage.input_tokens,
                             "completion": usage.output_tokens,
                             "total": usage.input_tokens + usage.output_tokens},
            )
        except Exception as e:
            latency = int((time.time() - t0) * 1000)
            err_str = str(e)
            # 403 = 地区限制，标记为 provider_unavailable
            if "403" in err_str or "forbidden" in err_str.lower():
                logger.warning(f"[claude] 403 地区限制，切换到备用 provider")
                return LLMResponse(success=False, provider="claude",
                                   model=self._model, error="provider_unavailable_403",
                                   latency_ms=latency)
            logger.error(f"[claude] error: {err_str[:200]}")
            return LLMResponse(success=False, provider="claude",
                               model=self._model, error=err_str[:200], latency_ms=latency)

    def generate_json(self, prompt: str, system_prompt=None,
                      temperature: float = 0.1, max_tokens: int = 2000) -> LLMResponse:
        resp = self.generate_text(prompt, system_prompt=system_prompt,
                                  temperature=temperature, max_tokens=max_tokens)
        if not resp.success:
            return resp
        parsed = _extract_json(resp.content or "")
        if parsed is None:
            return LLMResponse(success=False, provider="claude",
                               model=self._model, error="invalid_json",
                               content=resp.content, latency_ms=resp.latency_ms)
        resp.json_data = parsed
        return resp
