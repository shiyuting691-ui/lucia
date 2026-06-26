"""
LLMRouter — 多模型统一调度

配置（.env）：
  AI_PROVIDER_MODE=auto           # auto / claude / deepseek / qwen / rule
  AI_PRIMARY_PROVIDER=deepseek    # auto模式下的首选
  AI_FALLBACK_PROVIDERS=claude,rule

调度顺序（auto模式）：
  AI_PRIMARY_PROVIDER → AI_FALLBACK_PROVIDERS 按顺序 → rule_fallback

所有 LLM 调用必须通过 LLMRouter，不允许直接 new anthropic.Anthropic()。
"""
import os
import logging
import time
from typing import Optional

from .base import BaseLLMProvider, LLMResponse
from .anthropic_provider import AnthropicProvider
from .openai_compatible_provider import OpenAICompatibleProvider
from .rule_fallback_provider import RuleFallbackProvider

logger = logging.getLogger(__name__)

LOG_ENABLED = os.environ.get("LLM_LOG_ENABLED", "true").lower() == "true"

_PROVIDER_MAP = {
    "claude":        lambda: AnthropicProvider(),
    "deepseek":      lambda: OpenAICompatibleProvider("deepseek"),
    "qwen":          lambda: OpenAICompatibleProvider("qwen"),
    "rule_fallback": lambda: RuleFallbackProvider(),
    "rule":          lambda: RuleFallbackProvider(),
}


def _build_provider(name: str) -> Optional[BaseLLMProvider]:
    factory = _PROVIDER_MAP.get(name.strip().lower())
    if factory is None:
        logger.warning(f"[LLMRouter] 未知 provider: {name}")
        return None
    return factory()


class LLMRouter:
    """
    单例友好：每次创建都会读取最新的环境变量，方便测试时切换。
    """

    def __init__(self):
        mode     = os.environ.get("AI_PROVIDER_MODE", "auto").lower()
        primary  = os.environ.get("AI_PRIMARY_PROVIDER", "deepseek").lower()
        fallback = os.environ.get("AI_FALLBACK_PROVIDERS", "rule").lower()

        if mode == "auto":
            order = [primary] + [p.strip() for p in fallback.split(",") if p.strip()]
        else:
            # 指定模式：只用该 provider + rule 兜底
            order = [mode, "rule_fallback"]

        # 去重保序，末尾保证有 rule_fallback
        seen = set()
        self._order = []
        for name in order:
            if name not in seen:
                seen.add(name)
                self._order.append(name)
        if "rule_fallback" not in seen and "rule" not in seen:
            self._order.append("rule_fallback")

        logger.info(f"[LLMRouter] provider order: {self._order}")

    # ── 公共接口 ──────────────────────────────────────────────────────────────
    def generate_text(self, prompt: str, system_prompt=None,
                      temperature: float = 0.2, max_tokens: int = 2000,
                      task_type: str = "general") -> LLMResponse:
        return self._call("generate_text", prompt,
                          system_prompt=system_prompt,
                          temperature=temperature,
                          max_tokens=max_tokens,
                          task_type=task_type)

    def generate_json(self, prompt: str, system_prompt=None,
                      temperature: float = 0.1, max_tokens: int = 2000,
                      task_type: str = "general") -> LLMResponse:
        return self._call("generate_json", prompt,
                          system_prompt=system_prompt,
                          temperature=temperature,
                          max_tokens=max_tokens,
                          task_type=task_type)

    def chat(self, prompt: str, system_prompt=None,
             temperature: float = 0.2, max_tokens: int = 2000,
             task_type: str = "general") -> LLMResponse:
        """
        Backward-compatible text generation API.

        Older dashboard pages and agents call ``LLMRouter.chat(...)`` and read
        ``resp.text``. The router's canonical text API is now
        ``generate_text(...)``, so keep this thin adapter to avoid breaking
        those flows while the call sites are migrated.
        """
        return self.generate_text(
            prompt,
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            task_type=task_type,
        )

    def health_check_all(self) -> dict:
        results = {}
        for name in self._order:
            provider = _build_provider(name)
            if provider:
                results[name] = provider.health_check()
            else:
                results[name] = {"status": "unknown", "available": False}

        # 找到第一个可用的
        active = next(
            (n for n in self._order
             if results.get(n, {}).get("available")),
            "rule_fallback"
        )
        return {"providers": results, "active_provider": active,
                "order": self._order}

    # ── 内部调度 ─────────────────────────────────────────────────────────────
    def _call(self, method: str, prompt: str, task_type: str = "general",
              **kwargs) -> LLMResponse:
        last_error = None
        for name in self._order:
            provider = _build_provider(name)
            if not provider:
                continue
            if not provider.is_configured():
                logger.debug(f"[LLMRouter] skip {name}: not configured")
                continue

            t0 = time.time()
            try:
                fn   = getattr(provider, method)
                resp = fn(prompt, **kwargs)
            except Exception as e:
                resp = LLMResponse(success=False, provider=name, error=str(e))

            latency = int((time.time() - t0) * 1000)

            if resp.success:
                fallback_used = (name != self._order[0])
                if LOG_ENABLED:
                    self._log(task_type=task_type, provider=name,
                              model=resp.model or "", success=True,
                              latency_ms=latency, fallback_used=fallback_used,
                              token_usage=resp.token_usage)
                logger.info(f"[LLMRouter] ✅ {name} ({method}) latency={latency}ms"
                            + (" [fallback]" if fallback_used else ""))
                return resp

            # 失败，记录并继续
            last_error = resp.error
            if LOG_ENABLED:
                self._log(task_type=task_type, provider=name, model=resp.model or "",
                          success=False, error_type=_classify_error(resp.error or ""),
                          error_message=resp.error, latency_ms=latency, fallback_used=False)
            logger.warning(f"[LLMRouter] ❌ {name} failed: {resp.error} → 尝试下一个")

        # 全部失败（理论上 rule_fallback 不会失败）
        logger.error(f"[LLMRouter] 所有 provider 失败，最后错误: {last_error}")
        return LLMResponse(success=False, provider="none",
                           error=f"all_providers_failed: {last_error}")

    def _log(self, task_type: str, provider: str, model: str, success: bool,
             error_type: str = "", error_message: str = "", latency_ms: int = 0,
             fallback_used: bool = False, token_usage: dict = None):
        try:
            from database import save_llm_call_log
            save_llm_call_log({
                "task_type":         task_type,
                "provider":          provider,
                "model":             model,
                "success":           success,
                "error_type":        error_type,
                "error_message":     (error_message or "")[:500],
                "latency_ms":        latency_ms,
                "prompt_tokens":     (token_usage or {}).get("prompt", 0),
                "completion_tokens": (token_usage or {}).get("completion", 0),
                "total_tokens":      (token_usage or {}).get("total", 0),
                "fallback_used":     fallback_used,
            })
        except Exception as e:
            logger.debug(f"[LLMRouter] log write failed: {e}")


def _classify_error(err: str) -> str:
    err = err.lower()
    if "403" in err or "forbidden" in err or "unavailable_403" in err:
        return "forbidden_403"
    if "401" in err or "unauthorized" in err:
        return "unauthorized"
    if "timeout" in err:
        return "timeout"
    if "rate" in err or "429" in err:
        return "rate_limit"
    if "json" in err:
        return "invalid_json"
    if "not_configured" in err:
        return "not_configured"
    return "unknown"
